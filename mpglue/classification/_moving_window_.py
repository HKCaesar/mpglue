# cython: profile=False
# cython: cdivision=True
# cython: boundscheck=False
# cython: wraparound=False

from __future__ import division

import sys
from copy import copy

from cpython.array cimport array, clone
import numpy as np
cimport numpy as np
cimport cython

# from libc.math cimport cos, atan2
# from libc.stdlib cimport c_abs
# from libc.math cimport fabs
# from cython.parallel import prange, parallel

try:
    import cv2
except ImportError:
    raise ImportError('OpenCV must be installed')

old_settings = np.seterr(all='ignore')

DTYPE_intp = np.intp
ctypedef np.intp_t DTYPE_intp_t

DTYPE_int32 = np.int32
ctypedef np.int32_t DTYPE_int32_t

DTYPE_int16 = np.int16
ctypedef np.int16_t DTYPE_int16_t

DTYPE_int64 = np.int64
ctypedef np.int64_t DTYPE_int64_t

DTYPE_uint8 = np.uint8
ctypedef np.uint8_t DTYPE_uint8_t

DTYPE_float32 = np.float32
ctypedef np.float32_t DTYPE_float32_t   

DTYPE_float64 = np.float64
ctypedef np.float64_t DTYPE_float64_t


cdef extern from 'math.h':
   DTYPE_float32_t cos(DTYPE_float32_t a) nogil


cdef extern from 'math.h':
   DTYPE_float32_t atan2(DTYPE_float32_t a, DTYPE_float32_t b) nogil


cdef extern from 'stdlib.h':
    DTYPE_float32_t exp(DTYPE_float32_t x)


cdef inline DTYPE_float32_t _get_max_sample(DTYPE_float32_t s1, DTYPE_float32_t s2) nogil:
    return s2 if s2 > s1 else s1


cdef inline DTYPE_float32_t _multiply(DTYPE_float32_t a, DTYPE_float32_t b):
    return a * b


cdef inline DTYPE_float32_t _subtract(DTYPE_float32_t a, DTYPE_float32_t b) nogil:
    return a - b


cdef inline DTYPE_float32_t _collinearity(DTYPE_float32_t a, DTYPE_float32_t b) nogil:
    return a - b if (a - b) >= 0 else (a-b) * -1.


cdef inline DTYPE_float32_t int_min(DTYPE_float32_t a, DTYPE_float32_t b) nogil:
    return a if a <= b else b


cdef inline DTYPE_float32_t _nogil_get_max(DTYPE_float32_t a, DTYPE_float32_t b) nogil:
    return a if a >= b else b


cdef inline DTYPE_float32_t int_max(DTYPE_float32_t a, DTYPE_float32_t b) nogil:
    return a if a >= b else b


cdef inline DTYPE_float32_t _abs(DTYPE_float32_t m) nogil:
    return m*-1. if m < 0 else m


cdef inline Py_ssize_t _abs_pysize(Py_ssize_t m) nogil:
    return m*-1 if m < 0 else m


cdef inline int _abs_int(int m) nogil:
    return m*-1 if m < 0 else m


cdef inline DTYPE_float32_t _pow(DTYPE_float32_t m, DTYPE_float32_t n) nogil:
    return m**n


cdef inline DTYPE_float32_t _sqrt(DTYPE_float32_t m) nogil:
    return m**.5


cdef inline DTYPE_float32_t _spectral_distance(DTYPE_float32_t x1, DTYPE_float32_t x2) nogil:
    return _pow(x2 - x1, 2.)


cdef inline DTYPE_float32_t euclidean_distance(DTYPE_float32_t x1, DTYPE_float32_t x2, DTYPE_float32_t y1, DTYPE_float32_t y2) nogil:
    return ((x2 - x1)**2 + (y2 - y1)**2)**.5


cdef inline DTYPE_float32_t normalize_eu_dist(DTYPE_float32_t d, DTYPE_float32_t max_d):
    return _abs(d - max_d) / max_d


cdef inline DTYPE_float32_t euclidean_distance_color(DTYPE_float32_t x1, DTYPE_float32_t x2,
                                                     DTYPE_float32_t eu_dist):
    return ((x2 - x1)**2)**.5 * eu_dist


cdef inline DTYPE_float32_t simple_distance(DTYPE_float32_t x1, DTYPE_float32_t x2, DTYPE_float32_t eu_dist):
    return ((x2 - x1)**2) * eu_dist


cdef inline DTYPE_float32_t euclidean_distance_color_rgb(DTYPE_float32_t r1, DTYPE_float32_t g1, DTYPE_float32_t b1,
                                                         DTYPE_float32_t r2, DTYPE_float32_t g2, DTYPE_float32_t b2):
    return (((r2 - r1)**2) + ((g2 - g1)**2) + ((b2 - b1)**2)) **.5


cdef inline DTYPE_float32_t _translate_quadrant(DTYPE_float32_t coord2translate, DTYPE_float32_t wsh) nogil:
    return _abs(wsh - coord2translate)


cdef DTYPE_float32_t _get_line_angle(DTYPE_float32_t point1_y, DTYPE_float32_t point1_x,
                                     DTYPE_float32_t point2_y, DTYPE_float32_t point2_x,
                                     int wsh) nogil:

    """
    Args:
        point1_y (int): Center point row coordinate.
        point1_x (int): Center point column coordinate.
        point2_y (int): End point row coordinate.
        point2_x (int): End point column coordinate.
        wsh (int): The window size minus 1.
    
    point1: [y1, x1]
    point2: [y2, x2]
    
    (0,0) (0,1) (0,2) (0,3) (0,4)
    (1,0) (1,1) (1,2) (1,3) (1,4)
    (2,0) (2,1) (2,2) (2,3) (2,4)
    (3,0) (3,1) (3,2) (3,3) (3,4)
    (4,0) (4,1) (4,2) (4,3) (4,4)    
    
    if (0,0):
        x_diff = -1 * (2 - 0)
            = -2
        y_diff = 2 - 0
            = 2
    """

    cdef:
        DTYPE_float32_t x_diff
        DTYPE_float32_t y_diff
        # DTYPE_float32_t pi = 3.14159265

    # If necessary, translate from quadrant
    #   III or IV to quadrant I or II.
    if point2_y > point1_y:

        point2_y = _translate_quadrant(point2_y, float(wsh))
        point2_x = _translate_quadrant(point2_x, float(wsh))

    x_diff = _subtract(point1_x, point2_x) * -1.
    y_diff = _subtract(point1_y, point2_y)

    return atan2(y_diff, x_diff)    # * 180. / pi


# Define a function pointer to a metric.
ctypedef DTYPE_float32_t (*metric_ptr)(DTYPE_float32_t[:, ::1], DTYPE_intp_t, DTYPE_intp_t, DTYPE_intp_t, DTYPE_intp_t, DTYPE_float32_t[:, ::1], unsigned int) nogil


cdef tuple draw_line_tuple(Py_ssize_t y0, Py_ssize_t x0, Py_ssize_t y1, Py_ssize_t x1):

    """
    Graciously adapated from the Scikit-image team

    Generate line pixel coordinates.

    Parameters
    ----------
    y0, x0 : int
        Starting position (row, column).
    y1, x1 : int
        End position (row, column).

    Returns
    -------
    rr, cc : (N,) ndarray of int
        Indices of pixels that belong to the line.
        May be used to directly index into an array, e.g.
        ``img[rr, cc] = 1``.

    See Also
    --------
    line_aa : Anti-aliased line generator

    Examples
    --------
    >>> from skimage.draw import line
    >>> img = np.zeros((10, 10), dtype=np.uint8)
    >>> rr, cc = line(1, 1, 8, 8)
    >>> img[rr, cc] = 1
    >>> img
    array([[0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
           [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
           [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
           [0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
           [0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
           [0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
           [0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
           [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
           [0, 0, 0, 0, 0, 0, 0, 0, 1, 0],
           [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]], dtype=uint8)
    """

    cdef:
        char steep = 0
        Py_ssize_t x = x0
        Py_ssize_t y = y0
        Py_ssize_t dx = int(_abs(float(x1) - float(x0)))
        Py_ssize_t dy = int(_abs(float(y1) - float(y0)))
        Py_ssize_t sx, sy, d, i
        DTYPE_intp_t[:] rr, cc
        # array template = array('i')
        # array rr, cc

    if (x1 - x) > 0:
        sx = 1
    else:
        sx = -1

    if (y1 - y) > 0:
        sy = 1
    else:
        sy = -1

    if dy > dx:

        steep = 1
        x, y = y, x
        dx, dy = dy, dx
        sx, sy = sy, sx

    d = (2 * dy) - dx

    rr = np.zeros(int(dx)+1, dtype='intp')
    cc = rr.copy()
    # rr = clone(template, int(dx)+1, True)
    # cc = clone(template, int(dx)+1, True)

    for i in xrange(0, dx):

        if steep:
            rr[i] = x
            cc[i] = y
        else:
            rr[i] = y
            cc[i] = x

        while d >= 0:

            y += sy
            d -= 2 * dx

        x += sx
        d += 2 * dy

    rr[dx] = y1
    cc[dx] = x1

    return rr, cc


cdef void _extract_values_byte(DTYPE_uint8_t[:, :] block,
                               DTYPE_float32_t[:] values,
                               DTYPE_float32_t[:, :] rc_,
                               int fl) nogil:

    cdef:
        Py_ssize_t fi
        DTYPE_float32_t fi_, fj_

    for fi in range(0, fl):

        fi_ = rc_[0, fi]
        fj_ = rc_[1, fi]

        values[fi] = float(block[<int>fi_, <int>fj_])


cdef void _extract_values(DTYPE_float32_t[:, :] block,
                          DTYPE_float32_t[:] values,
                          DTYPE_float32_t[:, :] rc_,
                          int fl) nogil:

    cdef:
        Py_ssize_t fi
        DTYPE_float32_t fi_, fj_

    for fi in range(0, fl):

        fi_ = rc_[0, fi]
        fj_ = rc_[1, fi]

        values[fi] = block[<int>fi_, <int>fj_]


cdef void draw_line(Py_ssize_t y0, Py_ssize_t x0,
                    Py_ssize_t y1, Py_ssize_t x1,
                    DTYPE_float32_t[:, :] rc_) nogil:

    """
    Graciously adapated from the Scikit-image team

    Generate line pixel coordinates.

    Parameters
    ----------
    y0, x0 : int
        Starting position (row, column).
    y1, x1 : int
        End position (row, column).

    Returns
    -------
    rr, cc : (N,) ndarray of int
        Indices of pixels that belong to the line.
        May be used to directly index into an array, e.g.
        ``img[rr, cc] = 1``.

    See Also
    --------
    line_aa : Anti-aliased line generator

    Examples
    --------
    >>> from skimage.draw import line
    >>> img = np.zeros((10, 10), dtype=np.uint8)
    >>> rr, cc = line(1, 1, 8, 8)
    >>> img[rr, cc] = 1
    >>> img
    array([[0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
           [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
           [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
           [0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
           [0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
           [0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
           [0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
           [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
           [0, 0, 0, 0, 0, 0, 0, 0, 1, 0],
           [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]], dtype=uint8)
    """

    cdef:
        char steep = 0
        Py_ssize_t x = x0
        Py_ssize_t y = y0
        Py_ssize_t dx = _abs_pysize(x1 - x0)
        Py_ssize_t dy = _abs_pysize(y1 - y0)
        Py_ssize_t sx, sy, d, i

    if (x1 - x) > 0:
        sx = 1
    else:
        sx = -1

    if (y1 - y) > 0:
        sy = 1
    else:
        sy = -1

    if dy > dx:

        steep = 1
        x, y = y, x
        dx, dy = dy, dx
        sx, sy = sy, sx

    d = (2 * dy) - dx

    for i in range(0, dx):

        if steep:
            rc_[0, i] = x
            rc_[1, i] = y
        else:
            rc_[0, i] = y
            rc_[1, i] = x

        while d >= 0:

            y += sy
            d -= 2 * dx

        x += sx
        d += 2 * dy

    rc_[0, dx] = float(y1)
    rc_[1, dx] = float(x1)

    # Store the real line length
    rc_[2, 0] = float(dx + 1)


cdef list _direction_list():

    d1_idx = [2, 2, 2, 2, 2], [0, 1, 2, 3, 4]
    d2_idx = [3, 3, 2, 1, 1], [0, 1, 2, 3, 4]
    d3_idx = [4, 3, 2, 1, 0], [0, 1, 2, 3, 4]
    d4_idx = [4, 3, 2, 1, 0], [1, 1, 2, 3, 3]
    d5_idx = [0, 1, 2, 3, 4], [2, 2, 2, 2, 2]
    d6_idx = [0, 1, 2, 3, 4], [1, 1, 2, 3, 3]
    d7_idx = [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]
    d8_idx = [1, 1, 2, 3, 3], [0, 1, 2, 3, 4]

    return [d1_idx, d2_idx, d3_idx, d4_idx, d5_idx, d6_idx, d7_idx, d8_idx]


cdef dict _direction_dict():

    return {0: np.array([[0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0],
                         [1, 1, 1, 1, 1],
                         [0, 0, 0, 0, 0],
                         [0, 0, 0, 0, 0]], dtype='uint8'),
            1: np.array([[0, 0, 0, 0, 0],
                         [0, 0, 0, 1, 1],
                         [0, 0, 1, 0, 0],
                         [1, 1, 0, 0, 0],
                         [0, 0, 0, 0, 0]], dtype='uint8'),
            2: np.array([[0, 0, 0, 0, 1],
                         [0, 0, 0, 1, 0],
                         [0, 0, 1, 0, 0],
                         [0, 1, 0, 0, 0],
                         [1, 0, 0, 0, 0]], dtype='uint8'),
            3: np.array([[0, 0, 0, 1, 0],
                         [0, 0, 0, 1, 0],
                         [0, 0, 1, 0, 0],
                         [0, 1, 0, 0, 0],
                         [0, 1, 0, 0, 0]], dtype='uint8'),
            4: np.array([[0, 0, 1, 0, 0],
                         [0, 0, 1, 0, 0],
                         [0, 0, 1, 0, 0],
                         [0, 0, 1, 0, 0],
                         [0, 0, 1, 0, 0]], dtype='uint8'),
            5: np.array([[0, 1, 0, 0, 0],
                         [0, 1, 0, 0, 0],
                         [0, 0, 1, 0, 0],
                         [0, 0, 0, 1, 0],
                         [0, 0, 0, 1, 0]], dtype='uint8'),
            6: np.array([[1, 0, 0, 0, 0],
                         [0, 1, 0, 0, 0],
                         [0, 0, 1, 0, 0],
                         [0, 0, 0, 1, 0],
                         [0, 0, 0, 0, 1]], dtype='uint8'),
            7: np.array([[0, 0, 0, 0, 0],
                         [1, 1, 0, 0, 0],
                         [0, 0, 1, 0, 0],
                         [0, 0, 0, 1, 1],
                         [0, 0, 0, 0, 0]], dtype='uint8')}


# cdef inline DTYPE_uint8_t n_rows_cols(int pixel_index, int rows_cols, int block_size):
#     return rows_cols if (pixel_index + rows_cols) < block_size else block_size - pixel_index

# return 1. - exp(-eu_dist / y)


# @cython.boundscheck(False)
# @cython.wraparound(False)
# cdef DTYPE_float32_t get_contrast(DTYPE_float32_t cvg, DTYPE_float32_t[:] gbl):
#
#     cdef:
#         Py_ssize_t ii
#         v_length = gbl.shape[0] - 1
#         DTYPE_float32_t mu = gbl[0]
#
#     for ii in xrange(1, gbl):
#         mu += pow(cvg - gbl[ii], 2)
#
#     return mu / (v_length + 1)


cdef DTYPE_uint8_t _get_mean1d_int(DTYPE_uint8_t[:] block_list, int length):

    cdef:
        Py_ssize_t ii
        DTYPE_uint8_t s = block_list[0]

    for ii in range(1, length):
        s += block_list[ii]

    return s / length


cdef DTYPE_float32_t _get_mean1d(DTYPE_float32_t[:] block_list, int length) nogil:

    cdef:
        Py_ssize_t ii
        DTYPE_float32_t s = block_list[0]

    for ii in range(1, length):
        s += block_list[ii]

    return s / length


cdef DTYPE_float32_t _get_sum1df(DTYPE_float32_t[:] block_list, int length) nogil:

    cdef:
        Py_ssize_t fi
        DTYPE_float32_t s = block_list[0]

    for fi in range(1, length):
        s += block_list[fi]

    return s


cdef DTYPE_uint8_t _get_sum1d(DTYPE_uint8_t[:] block_list, int length) nogil:

    cdef:
        Py_ssize_t fi
        DTYPE_uint8_t s = block_list[0]

    for fi in xrange(1, length):
        s += block_list[fi]

    return s


cdef void _get_sum1d_f(DTYPE_float32_t[:] block_list,
                       int length,
                       DTYPE_float32_t[:] sums_array__) nogil:

    cdef:
        Py_ssize_t fi
        DTYPE_float32_t bv

    for fi in range(0, length):

        bv = block_list[fi]

        if bv <= 5:
            break

        sums_array__[0] += bv    # EGM sum
        sums_array__[1] += 1     # pixel count


cdef DTYPE_float32_t _get_std1d(DTYPE_float32_t[:] block_list, int length) nogil:

    cdef:
        Py_ssize_t ii
        DTYPE_float32_t block_list_mean = _get_mean1d(block_list, length)
        DTYPE_float32_t s = _pow(block_list[0] - block_list_mean, 2.)

    for ii in xrange(1, length):
        s += _pow(block_list[ii] - block_list_mean, 2.)

    return _sqrt(s / length)


cdef DTYPE_uint8_t _get_argmin1d(DTYPE_float32_t[:] block_list, int length):

    cdef:
        Py_ssize_t ii
        DTYPE_float32_t s = block_list[0]
        DTYPE_uint8_t argmin = 0
        DTYPE_float32_t b_samp

    with nogil:

        for ii in range(1, length-1):

            b_samp = block_list[ii]

            s = int_min(b_samp, s)

            if s == b_samp:
                argmin = ii

    return argmin


cdef np.ndarray[DTYPE_uint8_t, ndim=2, mode='c'] _mu_std(np.ndarray[DTYPE_float32_t, ndim=2, mode='c'] imb2calc, list direction_list, dict se_dict):

    # cdef:
    #     tuple d_directions, mu_std
    #
    #     # mean and standard deviation
    #     list mu_std_list = [cv2.meanStdDev(imb2calc[d_directions]) for d_directions in direction_list]
    #
    #     int min_std_idx = np.argmin([mu_std[1][0][0] for mu_std in mu_std_list])

    cdef:
        tuple d_directions
        DTYPE_float32_t[:] std_list = np.array([_get_std1d(imb2calc[d_directions], 5)
                                                for d_directions in direction_list], dtype='float32')
        int min_std_idx = _get_argmin1d(std_list, 5)

    return se_dict[min_std_idx]


cdef DTYPE_float32_t _morph_pass(DTYPE_float32_t[:, :] image_block, DTYPE_intp_t window_i, DTYPE_intp_t window_j,
                                 DTYPE_intp_t target_value, DTYPE_intp_t ignore_value,
                                 DTYPE_float32_t[:, :] weights, int hw):

    """
    Reference:
        D. Chaudhuri, N. K. Kushwaha, and A. Samal (2012) 'Semi-Automated Road
            Detection From High Resolution Satellite Images by Directional
            Morphological Enhancement and Segmentation Techniques', IEEE JOURNAL
            OF SELECTED TOPICS IN APPLIED EARTH OBSERVATIONS AND REMOTE SENSING,
            5(5), OCTOBER.
    """

    cdef:
        Py_ssize_t half = int(window_i / 2)
        list ds = _direction_list()
        dict se_dict = _direction_dict()
        np.ndarray[DTYPE_uint8_t, ndim=2, mode='c'] se = _mu_std(np.array(image_block).astype(np.float32), ds, se_dict)
        np.ndarray[DTYPE_uint8_t, ndim=2, mode='c'] im_b = cv2.morphologyEx(np.array(image_block).astype(np.uint8), cv2.MORPH_OPEN, se, iterations=1)
        # np.ndarray[DTYPE_uint8_t, ndim=2, mode='c'] im_b = pymorph.asfrec(np.array(image_block).astype(np.uint8), seq='CO', B=se, Bc=se, N=1)

    # se = _mu_std(im_b.astype(np.float32), ds, se_dict)

    # im_b = pymorph.asfrec(im_b, seq='OC', B=se, Bc=se, N=1)
    # im_b = cv2.morphologyEx(im_b, cv2.MORPH_DILATE, se, iterations=1)

    # se = _mu_std(im_b.astype(np.float32), ds, se_dict)

    # im_b = cv2.morphologyEx(im_b.astype(np.uint8), cv2.MORPH_DILATE, se, iterations=1)

    # se = _mu_std(im_b.astype(np.float32), ds, se_dict)

    # return float(pymorph.asfrec(im_b, seq='OC', B=se, Bc=se, N=1)[half, half])
    # return float(cv2.morphologyEx(im_b, cv2.MORPH_CLOSE, se, iterations=1)[half, half])
    return float(im_b[half, half])


cdef DTYPE_float32_t _get_median(DTYPE_float32_t[:, :] block, DTYPE_intp_t window_i, DTYPE_intp_t window_j,
                                 DTYPE_intp_t target_value, DTYPE_intp_t ignore_value,
                                 DTYPE_float32_t[:, :] weights, int hw):

    cdef:
        Py_ssize_t half = int((window_i * window_j) / 2)
        list sorted_list = sorted(list(np.asarray(block).ravel()))

    return sorted_list[half]


cdef DTYPE_float32_t _get_min(DTYPE_float32_t[:, ::1] block,
                              DTYPE_intp_t window_i,
                              DTYPE_intp_t window_j,
                              DTYPE_intp_t target_value,
                              DTYPE_intp_t ignore_value,
                              DTYPE_float32_t[:, ::1] weights,
                              unsigned int hw) nogil:

    cdef:
        Py_ssize_t ii, jj
        DTYPE_float32_t su = 999999.

    if ignore_value != -9999:

        for ii in range(0, window_i):
            for jj in range(0, window_j):

                if block[ii, jj] != ignore_value:
                    su = int_min(block[ii, jj], su)

    else:

        for ii in range(0, window_i):
            for jj in range(0, window_j):

                su = int_min(block[ii, jj], su)

    return su


cdef DTYPE_float32_t _get_max(DTYPE_float32_t[:, ::1] block,
                              DTYPE_intp_t window_i,
                              DTYPE_intp_t window_j,
                              DTYPE_intp_t target_value,
                              DTYPE_intp_t ignore_value,
                              DTYPE_float32_t[:, ::1] weights,
                              unsigned int hw) nogil:

    cdef:
        Py_ssize_t ii, jj
        DTYPE_float32_t su = -999999.

    if ignore_value != -9999:

        for ii in range(0, window_i):
            for jj in range(0, window_j):

                if block[ii, jj] != ignore_value:
                    su = int_max(block[ii, jj], su)

    else:

        for ii in range(0, window_i):
            for jj in range(0, window_j):

                su = int_max(block[ii, jj], su)

    return su


cdef DTYPE_uint8_t _fill_holes(DTYPE_uint8_t[:, :] block,
                               DTYPE_uint8_t[:] rr,
                               DTYPE_uint8_t[:] cc,
                               int window_size,
                               int n_neighbors) nogil:

    cdef:
        Py_ssize_t ii, jj
        int center = <int>(window_size / 2.)
        DTYPE_uint8_t s = 0
        DTYPE_uint8_t fill_value = block[center, center]

    if fill_value == 0:

        for ii in range(0, n_neighbors):
            s += block[rr[ii], cc[ii]]

        # Fill the pixel if it
        #   is surrounded.
        if s == n_neighbors:
            fill_value = 1

    return fill_value


cdef DTYPE_uint8_t _get_sum_int(DTYPE_uint8_t[:, :] block, unsigned int window_i, unsigned int window_j):

    cdef:
        Py_ssize_t ii, jj
        DTYPE_uint8_t su = 0

    # with nogil, parallel(num_threads=window_i):
    #
    #     for ii in prange(0, window_i, schedule='static'):
    for ii in xrange(0, window_i):

        for jj in xrange(0, window_j):

            su += block[ii, jj]

    return su


cdef DTYPE_uint8_t _get_sum_uint8(DTYPE_uint8_t[:, :] block, DTYPE_intp_t window_i, DTYPE_intp_t window_j):

    cdef:
        Py_ssize_t ii, jj
        DTYPE_uint8_t su = 0

    # with nogil, parallel(num_threads=window_i):
    #
    #     for ii in prange(0, window_i, schedule='static'):
    for ii in xrange(0, window_i):

        for jj in xrange(0, window_j):

            su += block[ii, jj]

    return su


cdef DTYPE_float32_t _get_sum(DTYPE_float32_t[:, ::1] block,
                              DTYPE_intp_t window_i,
                              DTYPE_intp_t window_j,
                              DTYPE_intp_t target_value,
                              DTYPE_intp_t ignore_value,
                              DTYPE_float32_t[:, ::1] weights,
                              unsigned int hw) nogil:

    cdef:
        Py_ssize_t ii, jj
        DTYPE_float32_t su = 0.

    if ignore_value != -9999:

        # with nogil, parallel(num_threads=window_i):
        #
        #     for ii in prange(0, window_i, schedule='static'):
        for ii in range(0, window_i):

            for jj in range(0, window_j):

                if block[ii, jj] != ignore_value:
                    su += block[ii, jj]

    else:

        # with nogil, parallel(num_threads=window_i):
        #
        #     for ii in prange(0, window_i, schedule='static'):
        for ii in range(0, window_i):

            for jj in range(0, window_j):

                su += block[ii, jj]

    return su


cdef DTYPE_float32_t _get_mean(DTYPE_float32_t[:, ::1] block,
                               DTYPE_intp_t window_i,
                               DTYPE_intp_t window_j, 
                               DTYPE_intp_t target_value,
                               DTYPE_intp_t ignore_value, 
                               DTYPE_float32_t[:, ::1] weights,
                               unsigned int hw) nogil:

    cdef:
        Py_ssize_t ii, jj
        DTYPE_float32_t su = 0.
        int good_values = 0

    if target_value != -9999:
        if block[hw, hw] != target_value:
            return block[hw, hw]

    if ignore_value != -9999:

        for ii in range(0, window_i):
            for jj in range(0, window_j):

                if block[ii, jj] != ignore_value:

                    su += block[ii, jj] * weights[ii, jj]
                    good_values += 1

    else:

        for ii in range(0, window_i):
            for jj in range(0, window_j):

                su += block[ii, jj] * weights[ii, jj]

        good_values = window_i * window_j

    if good_values == 0:
        return 0.
    else:
        return su / good_values


cdef DTYPE_float32_t _get_distance(DTYPE_float32_t[:, :] block_dist,
                                   DTYPE_intp_t window_ij,
                                   int hw,
                                   DTYPE_float32_t[:, ::1] dist_weights,
                                   DTYPE_float32_t no_data_value) nogil:

    cdef:
        Py_ssize_t ii, jj
        DTYPE_float32_t sdist = 0.
        DTYPE_float32_t wdist = 0.
        DTYPE_float32_t bcv = block_dist[hw, hw]
        DTYPE_float32_t window_sum = bcv
        DTYPE_float32_t bnv, dw
        Py_ssize_t good_count = 0

    # Center pixel
    if bcv == no_data_value:
        return 0.

    for ii in range(0, window_ij):

        for jj in range(0, window_ij):

            if (ii == hw) and (jj == hw):
                continue

            bnv = block_dist[ii, jj]

            # Get the spectral distance between
            #   the center pixel and the
            #   neighboring pixels.
            if bnv != no_data_value:

                dw = dist_weights[ii, jj]
                sdist += _spectral_distance(bnv, bcv) * dw

                window_sum += bnv
                wdist += dw

                good_count += 1

    if sdist == 0:
        return 0.
    else:
        return (sdist / wdist) * (window_sum / float(good_count))


cdef DTYPE_float32_t _get_distance_rgb(DTYPE_float32_t[:, :, :] block,
                                       DTYPE_intp_t window_i, DTYPE_intp_t window_j,
                                       int hw, int dims):

    cdef:
        Py_ssize_t ii, jj
        # DTYPE_float32_t d
        # DTYPE_float32_t max_d = euclidean_distance(hw, 0., hw, 0.)
        DTYPE_float32_t[:] hw_values = np.zeros(3, dtype='float32')
        DTYPE_float32_t color_d = 0.
        # DTYPE_float32_t avg_d = 0.
        # DTYPE_float32_t block_max = _get_max(block, window_i, window_j, ignore_value, weights, hw)
        # DTYPE_float32_t block_min = _get_min(block, window_i, window_j, ignore_value, weights, hw)
        # DTYPE_float32_t max_color_dist = euclidean_distance_color(block_min, block_max, 1.)
        # DTYPE_float32_t max_color_dist = float(dims)**.5  # sqrt((1-0)^2 + (1-0)^2 + (1-0)^2)
        # DTYPE_float32_t max_color_dist = 0.

    # Center values
    hw_values[0] = block[0, hw, hw]
    hw_values[1] = block[1, hw, hw]
    hw_values[2] = block[2, hw, hw]

    for ii in xrange(0, window_i):

        for jj in xrange(0, window_j):

            if (ii == hw) and (jj == hw):
                continue

            # Get the Euclidean distance between the center pixel
            #   and the surrounding pixels.
            # d = euclidean_distance(hw, jj, hw, ii)

            # d = normalize_eu_dist(d, max_d)
            #
            # if d == 0:
            #     d = .01

            # Get the distance between colors.
            color_d += euclidean_distance_color_rgb(hw_values[0], hw_values[1], hw_values[2],
                                                    block[0, ii, jj], block[1, ii, jj], block[2, ii, jj])

            # max_color_dist = max(color_d, max_color_dist)
            #
            # avg_d += color_d

    # Get the block average and
    #   normalize the block average.
    return color_d / ((hw * hw) - 1)


cdef int cy_argwhere(DTYPE_uint8_t[:, :] array1,
                     DTYPE_uint8_t[:, :] array2,
                     int dims,
                     DTYPE_int16_t[:, :] angles_dict) nogil:

    cdef:
        Py_ssize_t i_, j_, i_idx, j_idx
        int counter = 1

    for i_ in range(0, dims):
        for j_ in range(0, dims):

            if (array1[i_, j_] == 1) and (array2[i_, j_] == 0):

                if counter > 1:

                    i_idx = (i_idx + i_) / counter
                    j_idx = (j_idx + j_) / counter

                else:

                    i_idx = i_ + 0
                    j_idx = j_ + 0

                counter += 1

    if counter == 1:
        return 9999
    else:
        return angles_dict[i_idx, j_idx]


cdef tuple close_end(DTYPE_uint8_t[:, :] edge_block,
                     DTYPE_uint8_t[:, :] endpoints_block,
                     DTYPE_uint8_t[:, :] gradient_block,
                     int angle, int center, DTYPE_intp_t[:] dummy,
                     DTYPE_intp_t[:] h_r, DTYPE_intp_t[:] h_c, DTYPE_intp_t[:] d_c,
                     DTYPE_int16_t[:, :] angles_dict, int min_egm, int max_gap):

    cdef:
        Py_ssize_t ip, rr_shape, ip_, jp_
        DTYPE_intp_t[:] rr_, cc_, hr1, hr2
        int mtotal = 3      # The total number of orthogonal pixels required to connect a point with orthogonal lines.
        int connect_angle
        int min_line = 3    # The minimum line length to connect a point to an edge with sufficient EGM

    if angle == 90:

        ip_ = -1
        jp_ = 0
        hr1 = h_r
        hr2 = h_c

    elif angle == -90:

        ip_ = 1
        jp_ = 0
        hr1 = h_r
        hr2 = h_c

    elif angle == 180:

        ip_ = 0
        jp_ = -1
        hr1 = h_c
        hr2 = h_r

    elif angle == -180:

        ip_ = 0
        jp_ = 1
        hr1 = h_c
        hr2 = h_r

    elif angle == 135:

        ip_ = -1
        jp_ = -1
        hr1 = d_c
        hr2 = h_c

    elif angle == -135:

        ip_ = 1
        jp_ = 1
        hr1 = d_c
        hr2 = h_c

    elif angle == 45:

        ip_ = -1
        jp_ = 1
        hr1 = h_c
        hr2 = h_c

    elif angle == -45:

        ip_ = 1
        jp_ = -1
        hr1 = h_c
        hr2 = h_c

    else:
        return dummy, dummy, 0, 9999

    for ip in xrange(1, max_gap-2):

        if edge_block[center+(ip*ip_), center+(ip*jp_)] == 1:

            # Draw a line that would connect the two points.
            rr_, cc_ = draw_line_tuple(center, center, center+(ip*ip_), center+(ip*jp_))

            rr_shape = rr_.shape[0]

            # Connect the points if the line is
            #   small and has edge magnitude.
            if rr_shape <= min_line:

                if _get_mean1d_int(extract_values(gradient_block, rr_, cc_, rr_shape),
                                   rr_shape) >= min_egm:

                    return rr_, cc_, 1, 9999

            # Check if it is an endpoint or an edge.
            connect_angle = cy_argwhere(edge_block[center+(ip*ip_)-2:center+(ip*ip_)+3,
                                                   center+(ip*jp_)-2:center+(ip*jp_)+3],
                                        endpoints_block[center+(ip*ip_)-2:center+(ip*ip_)+3,
                                                        center+(ip*jp_)-2:center+(ip*jp_)+3], 3, angles_dict)

            # Connect lines of any length with
            #   inverse or orthogonal angles.
            if angle + connect_angle == 0 or \
                            _get_sum1d(extract_values(edge_block[center+(ip*ip_)-2:center+(ip*ip_)+3,
                                                                 center+(ip*jp_)-2:center+(ip*jp_)+3],
                                                      hr1, hr2, 5), 5) >= mtotal:

                if _get_mean1d_int(extract_values(gradient_block, rr_, cc_, rr_shape), rr_shape) >= min_egm:
                    return rr_, cc_, 1, 9999

            break

    return dummy, dummy, 0, 9999


cdef DTYPE_float32_t[:] extract_values_f(DTYPE_float32_t[:, :] block, DTYPE_intp_t[:] rr_, DTYPE_intp_t[:] cc_, int fl):

    cdef:
        Py_ssize_t fi, fi_, fj_
        DTYPE_float32_t[:] values = np.zeros(fl, dtype='float32')

    with nogil:

        for fi in range(0, fl):

            fi_ = rr_[fi]
            fj_ = cc_[fi]

            values[fi] = block[fi_, fj_]

    return values


cdef DTYPE_uint8_t[:] extract_values(DTYPE_uint8_t[:, :] block, DTYPE_intp_t[:] rr_, DTYPE_intp_t[:] cc_, int fl):

    cdef:
        Py_ssize_t fi, fi_, fj_
        DTYPE_uint8_t[:] values = np.zeros(fl, dtype='uint8')

    for fi in xrange(0, fl):

        fi_ = rr_[fi]
        fj_ = cc_[fi]

        values[fi] = block[fi_, fj_]

    return values


cdef DTYPE_uint8_t[:, :] fill_block(DTYPE_uint8_t[:, :] block2fill,
                                    DTYPE_intp_t[:] rr_,
                                    DTYPE_intp_t[:] cc_,
                                    int fill_value):

    cdef:
        Py_ssize_t fi, fi_, fj_
        int fl = rr_.shape[0]

    for fi in range(0, fl):

        fi_ = rr_[fi]
        fj_ = cc_[fi]

        block2fill[fi_, fj_] = fill_value

    return block2fill


cdef tuple _link_endpoints(DTYPE_uint8_t[:, :] edge_block,
                           DTYPE_uint8_t[:, :] endpoints_block,
                           DTYPE_uint8_t[:, :] gradient_block,
                           unsigned int window_size,
                           DTYPE_int16_t[:, :] angles_dict,
                           DTYPE_intp_t[:] h_r, DTYPE_intp_t[:] h_c, DTYPE_intp_t[:] d_c,
                           int min_egm, int smallest_allowed_gap, int medium_allowed_gap):

    cdef:
        Py_ssize_t ii, jj, ii_, jj_, rr_shape
        unsigned int smallest_gap = window_size * window_size   # The smallest gap found
        unsigned int center = int(window_size / 2)
        int center_angle, connect_angle, ss, match
        DTYPE_intp_t[:] rr, cc, rr_, cc_
        DTYPE_intp_t[:] dummy = np.array([], dtype='intp')

    if smallest_allowed_gap > window_size:
        smallest_allowed_gap = window_size

    if medium_allowed_gap > window_size:
        medium_allowed_gap = window_size

    # Get the origin angle of the center endpoint.
    center_angle = cy_argwhere(edge_block[center-1:center+2, center-1:center+2],
                               endpoints_block[center-1:center+2, center-1:center+2],
                               3, angles_dict)

    if center_angle == 9999:
        return edge_block, endpoints_block

    # There must be at least two endpoints
    #   in the block.
    if _get_sum_int(endpoints_block, window_size, window_size) > 1:

        for ii in xrange(0, window_size-2):

            for jj in xrange(0, window_size-2):

                # Cannot connect to direct neighbors or itself.
                if (_abs(float(ii) - float(center)) <= 1) and (_abs(float(jj) - float(center)) <= 1):
                    continue

                # Cannot connect with edges because we cannot
                #   get the angle.
                if (ii == 0) or (ii == window_size-1) or (jj == 0) or (jj == window_size-1):
                    continue

                # Located another endpoint.
                if endpoints_block[ii, jj] == 1:

                    # CONNECT ENDPOINTS WITH SMALL GAP

                    # Draw a line between the two endpoints.
                    rr, cc = draw_line_tuple(center, center, ii, jj)

                    rr_shape = rr.shape[0]

                    # (2) ONLY CONNECT THE SMALLEST LINE POSSIBLE
                    if rr_shape >= smallest_gap:
                        continue

                    # (3) CHECK IF THE CONNECTING LINE CROSSES OTHER EDGES
                    if _get_sum1d(extract_values(edge_block, rr, cc, rr_shape), rr_shape) > 2:
                        continue

                    # Check the angles if the gap is large.

                    # 3) CONNECT POINTS WITH SIMILAR ANGLES
                    connect_angle = cy_argwhere(edge_block[ii-1:ii+2, jj-1:jj+2],
                                                endpoints_block[ii-1:ii+2, jj-1:jj+2],
                                                3, angles_dict)

                    if connect_angle == 9999:
                        continue

                    # Don't accept same angles.
                    if center_angle == connect_angle:
                        continue

                    # For small gaps allow any angle as long
                    #   as there is sufficient EGM.
                    if rr_shape <= smallest_allowed_gap:

                        # There must be edge contrast along the line.
                        if _get_mean1d_int(extract_values(gradient_block, rr, cc, rr_shape), rr_shape) > min_egm:

                            rr_, cc_ = rr.copy(), cc.copy()

                            ii_ = copy(ii)  # ii + 0
                            jj_ = copy(jj)  # jj + 0

                            smallest_gap = min(rr_shape, smallest_gap)

                    # For medium-sized gaps allow similar angles, but no
                    #   asymmetric angles.
                    elif rr_shape <= medium_allowed_gap:

                        match = 0

                        # Northwest or southeast of center point
                        if ((ii < center-2) and (jj < center-2)) or ((ii > center+2) and (jj > center+2)):

                            if (center_angle + connect_angle == 0) or \
                                ((center_angle == 180) and (connect_angle == -135)) or \
                                ((center_angle == 90) and (connect_angle == -135)) or \
                                ((center_angle == -180) and (connect_angle == 135)) or \
                                ((center_angle == -90) and (connect_angle == 135)):

                                match = 1

                        # North or south of center point
                        elif ((ii < center-2) and (center-2 < jj < center+2)) or \
                            ((ii > center+2) and (center-2 < jj < center + 2)):

                            if (center_angle + connect_angle == 0) or \
                                ((center_angle == 90) and (connect_angle == -135)) or \
                                ((center_angle == 90) and (connect_angle == -45)) or \
                                ((center_angle == -90) and (connect_angle == 135)) or \
                                ((center_angle == -90) and (connect_angle == 45)):

                                match = 1

                        # Northeast or southwest of center point
                        elif ((ii < center-2) and (jj > center+2)) or ((ii > center+2) and (jj < center-2)):

                            if (center_angle + connect_angle == 0) or \
                                ((center_angle == -180) and (connect_angle == -45)) or \
                                ((center_angle == 90) and (connect_angle == -45)) or \
                                ((center_angle == 180) and (connect_angle == 45)) or \
                                ((center_angle == -90) and (connect_angle == 45)):

                                match = 1

                        # East or west of center point
                        elif ((center-2 < ii < center+2) and (jj > center+2)) or \
                            ((center-2 < ii < center+2) and (jj < center-2)):

                            if (center_angle + connect_angle == 0) or \
                                ((center_angle == 180) and (connect_angle == -135)) or \
                                ((center_angle == 180) and (connect_angle == 45)) or \
                                ((center_angle == -180) and (connect_angle == 135)) or \
                                ((center_angle == -180) and (connect_angle == -45)):

                                match = 1

                        if match == 1:

                            # There must be edge contrast along the line.
                            # if _get_mean1d_int(extract_values(gradient_block, rr, cc, rr_shape),
                            #                    rr_shape) >= min_egm:

                            rr_, cc_ = rr.copy(), cc.copy()

                            ii_ = copy(ii)  # ii + 0
                            jj_ = copy(jj)  # jj + 0

                            smallest_gap = min(rr_shape, smallest_gap)

                    # All other gaps must be inverse angles and have
                    #   a mean edge gradient magnitude over the minimum
                    #   required.
                    else:

                        # All other inverse angles.
                        if center_angle + connect_angle == 0:

                            # There must be edge contrast along the line.
                            if _get_mean1d_int(extract_values(gradient_block, rr, cc, rr_shape),
                                               rr_shape) >= min_egm:

                                rr_, cc_ = rr.copy(), cc.copy()

                                ii_ = copy(ii)  # ii + 0
                                jj_ = copy(jj)  # jj + 0

                                smallest_gap = min(rr_shape, smallest_gap)

    # TRY TO CLOSE GAPS FROM ENDPOINTS

    # At this juncture, there doesn't have to
    #   be two endpoints.
    if smallest_gap == window_size * window_size:

        rr_, cc_, ss, ii_ = close_end(edge_block, endpoints_block, gradient_block, center_angle,
                                      center, dummy, h_r, h_c, d_c, angles_dict, min_egm, center)

        if ss == 1:
            smallest_gap = 0

    if smallest_gap < window_size * window_size:

        edge_block = fill_block(edge_block, rr_, cc_, 1)

        # Remove the endpoint
        endpoints_block[center, center] = 0

        if ii_ < 9999:
            endpoints_block[ii_, jj_] = 0

    return edge_block, endpoints_block


cdef DTYPE_float32_t _duda_operator(DTYPE_float32_t[:, ::1] block,
                                    DTYPE_intp_t window_i,
                                    DTYPE_intp_t window_j,
                                    DTYPE_intp_t target_value,
                                    DTYPE_intp_t ignore_value,
                                    DTYPE_float32_t[:, ::1] weights,
                                    unsigned int hw) nogil:

    cdef:
        DTYPE_float32_t duda = 0.
        DTYPE_float32_t a, b, c

    a = block[hw, hw]

    b = block[0, hw]
    c = block[window_i-1, hw]

    if b < a > c:
        duda = _nogil_get_max(duda, 2.*a-b-c)

    b = block[0, 0]
    c = block[window_i-1, window_j-1]

    if b < a > c:
        duda = _nogil_get_max(duda, 2.*a-b-c)

    b = block[hw, 0]
    c = block[hw, window_j-1]

    if b < a > c:
        duda = _nogil_get_max(duda, 2.*a-b-c)

    b = block[window_i-1, 0]
    c = block[0, window_j-1]

    if b < a > c:
        duda = _nogil_get_max(duda, 2.*a-b-c)

    return duda


cdef DTYPE_float32_t _get_percent(DTYPE_float32_t[:, ::1] block,
                                  DTYPE_intp_t window_i,
                                  DTYPE_intp_t window_j,
                                  DTYPE_intp_t target_value,
                                  DTYPE_intp_t ignore_value,
                                  DTYPE_float32_t[:, ::1] weights,
                                  unsigned int hw) nogil:

    cdef:
        Py_ssize_t ii, jj
        DTYPE_float32_t su = 0.
        unsigned int good_values = 0

    if ignore_value != -9999:

        for ii in range(0, window_i):
            for jj in range(0, window_j):

                if block[ii, jj] != ignore_value:
                    su += block[ii, jj]
                    good_values += 1

    else:

        for ii in range(0, window_i):

            for jj in range(0, window_j):

                su += block[ii, jj]

        good_values = window_i * window_j

    return (su / good_values) * 100.


cdef DTYPE_float32_t[:] _get_unique(DTYPE_float32_t[:, :] block, DTYPE_intp_t window_i, DTYPE_intp_t window_j):

    cdef:
        Py_ssize_t ii, jj, cc
        DTYPE_float32_t[:] unique_values = np.zeros(window_i*window_j, dtype='float32')-9999.
        int counter = 0
        bint u_found

    for ii in xrange(0, window_i):

        for jj in xrange(0, window_j):

            if counter == 0:

                unique_values[counter] = block[ii, jj]
                counter += 1

            else:

                u_found = False

                for cc in xrange(0, counter):

                    if unique_values[cc] == block[ii, jj]:
                        u_found = True
                        break

                if not u_found:
                    unique_values[counter] = block[ii, jj]
                    counter += 1

    return unique_values[:counter]


cdef DTYPE_float32_t _get_majority(DTYPE_float32_t[:, :] block, DTYPE_intp_t window_i, DTYPE_intp_t window_j,
                                   DTYPE_intp_t target_value, DTYPE_intp_t ignore_value,
                                   DTYPE_float32_t[:, :] weights, int hw):

    cdef:
        Py_ssize_t ii, jj, max_idx, kk
        DTYPE_float32_t[:] unique_values = _get_unique(block, window_i, window_j)
        int n_unique = unique_values.shape[0]
        DTYPE_uint8_t[:] count_list = np.zeros(n_unique, dtype='uint8')
        Py_ssize_t samples = window_i * window_j
        Py_ssize_t half_samples = samples / 2
        DTYPE_float32_t block_value, max_count

    with nogil:

        if target_value != -9999:
            if block[hw, hw] != target_value:
                return block[hw, hw]

        if ignore_value != -9999:

            for ii in range(0, window_i):

                for jj in range(0, window_j):

                    block_value = block[ii, jj]

                    if block_value != ignore_value:

                        for kk in range(0, n_unique):

                            if unique_values[kk] == block_value:
                                count_list[kk] += 1

                                if count_list[kk] > half_samples:
                                    return block_value

                                break

        else:

            for ii in range(0, window_i):

                for jj in range(0, window_j):

                    block_value = block[ii, jj]

                    for kk in range(0, n_unique):

                        if unique_values[kk] == block_value:
                            count_list[kk] += 1

                            if count_list[kk] > half_samples:
                                return block_value

                            break

    # Get the largest count.
    max_count = count_list[0]
    max_idx = 0
    for kk in range(1, n_unique):

        if count_list[kk] > max_count:
            max_idx = copy(kk)

    return unique_values[max_idx]


cdef np.ndarray[DTYPE_uint8_t, ndim=2] link_window(DTYPE_uint8_t[:, :] edge_image,
                                                   unsigned int window_size,
                                                   DTYPE_uint8_t[:, :] endpoint_image,
                                                   DTYPE_uint8_t[:, :] gradient_image,
                                                   int min_egm, int smallest_allowed_gap,
                                                   int medium_allowed_gap):

    """
    Links endpoints
    """

    cdef:
        int rows = edge_image.shape[0]
        int cols = edge_image.shape[1]
        Py_ssize_t cij, isub, jsub, iplus, jplus
        unsigned int half_window = int(window_size / 2)
        DTYPE_int64_t[:, :] endpoint_idx
        DTYPE_int64_t[:] endpoint_row
        int endpoint_idx_rows
        DTYPE_uint8_t[:, :] edge_block, ep_block

        DTYPE_int16_t[:, :] angles_dict = np.array([[-135, -90, -45],
                                                    [-180, 0, 180],
                                                    [45, 90, 135]], dtype='int16')

        DTYPE_intp_t[:] h_r = np.array([2, 2, 2, 2, 2], dtype='intp')
        DTYPE_intp_t[:] h_c = np.array([0, 1, 2, 3, 4], dtype='intp')
        DTYPE_intp_t[:] d_c = np.array([4, 3, 2, 1, 0], dtype='intp')

    endpoint_idx = np.argwhere(np.asarray(endpoint_image) == 1)
    endpoint_idx_rows = endpoint_idx.shape[0]

    for cij in xrange(0, endpoint_idx_rows):

        endpoint_row = endpoint_idx[cij]

        isub = endpoint_row[0] - half_window
        iplus = endpoint_row[0] + half_window
        jsub = endpoint_row[1] - half_window
        jplus = endpoint_row[1] + half_window

        # Bounds checking
        if (isub < 0) or (iplus >= rows) or (jsub < 0) or (jplus >= cols):
            continue

        edge_block, ep_block = _link_endpoints(edge_image[isub:isub+window_size, jsub:jsub+window_size],
                                               endpoint_image[isub:isub+window_size, jsub:jsub+window_size],
                                               gradient_image[isub:isub+window_size, jsub:jsub+window_size],
                                               window_size, angles_dict, h_r, h_c, d_c,
                                               min_egm, smallest_allowed_gap, medium_allowed_gap)

        edge_image[isub:isub+window_size, jsub:jsub+window_size] = edge_block
        endpoint_image[isub:isub+window_size, jsub:jsub+window_size] = ep_block

    return np.uint8(edge_image)


cdef Py_ssize_t _orthogonal_opt(DTYPE_float32_t y1,
                                DTYPE_float32_t x1,
                                DTYPE_float32_t y2,
                                DTYPE_float32_t x2,
                                DTYPE_float32_t center_value,
                                int half_window,
                                int window_size,
                                DTYPE_float32_t[:, :] edge_image_block,
                                DTYPE_float32_t[:, :] rc) nogil:

    """
    Finds the maximum number of pixels along an orthogonal
    line that are less than the center edge value

    Args:
        points of the line
        N: length of the line
        center_value
    """

    cdef:
        Py_ssize_t y3_, x3_, y3, x3, li
        int rc_shape
        Py_ssize_t max_consecutive = 0
        DTYPE_float32_t[:] line_values

    # First, translate the coordinate
    #   to the Cartesian plane.
    y3_ = half_window - <int>y2         # = 2
    x3_ = -(half_window - <int>x2)      # = -2

    # Next, shift the coordinates 90 degrees.
    y3 = x3_            # = -2
    x3 = y3_ * -1       # = -2

    # Translate back to a Python grid.
    y3 = <int>(_abs(float(y3 - half_window)))       # abs(-2 - 2) = 4
    x3 = x3 + half_window                           # -2 + 2 = 0

    # Find the orthogonal line
    # Draw a line from the center pixel
    #   to the current end coordinate.
    draw_line(<int>y1, <int>y2, <int>y3, <int>x3, rc)

    # Get the current line length.
    rc_shape = <int>rc[2, 0]

    # row of zeros, up to the line length
    line_values = rc[3, :rc_shape]
    
    # Extract the values along the line.
    _extract_values(edge_image_block, line_values, rc, rc_shape)
    
    # Get the the maximum number of consecutive pixels
    #   with values less than the center pixel.
    for li in range(1, rc_shape):

        if line_values[li] >= center_value:
            break
        else:
            max_consecutive += 1

    return max_consecutive


cdef void _fill_zeros(DTYPE_float32_t[:] array2fill, int array_length):

    cdef:
        Py_ssize_t fill_idx

    for fill_idx in range(0, array_length):
        array2fill[fill_idx] = 0.


cdef void _optimal_edge_orientation(DTYPE_float32_t[:, :] edge_image_block,
                                    DTYPE_uint8_t[:] indices,
                                    int half_window,
                                    int window_size,
                                    DTYPE_float32_t[:, :] rc,
                                    DTYPE_float32_t[:] vars_array_,
                                    DTYPE_float32_t[:] sums_array_):

    """
    Returns:
        max_sum:  Maximum edge value sum along the optimal angle
        line_angle:  The optimal line angle
        n_opt:  The number of pixels along the optimal line angle
        nc_opt:  The maximum number pixels with an edge value less than the center
    """

    cdef:
        Py_ssize_t end_idx, end_idx_r, pix_idx_r, j__, nc_opt
        int rc_shape
        DTYPE_float32_t si_sum
        DTYPE_float32_t line_angle = 0.
        DTYPE_float32_t si_max = -9999.
        DTYPE_float32_t center_value = edge_image_block[half_window, half_window]
        DTYPE_float32_t[:] line_values
        DTYPE_float32_t theta_opt

    # Ensure empty
    _fill_zeros(vars_array_, 3)

    # Iterate over top and bottom rows.
    for end_idx in range(0, 2):

        # Get the end index (0 or window size-1).
        end_idx_r = indices[end_idx]

        # Iterate over the window length.
        for pix_idx_r in range(0, window_size):

            # Ensure empty
            _fill_zeros(sums_array_, 2)

            with nogil:

                # Draw a line from the center pixel
                #   to the current end coordinate.
                draw_line(half_window, half_window, end_idx_r, pix_idx_r, rc)

                # Get the current line length.
                rc_shape = <int>rc[2, 0]

            # row of zeros, up to the line length
            line_values = rc[3, :rc_shape]

            with nogil:

                # Extract the values along the line.
                _extract_values(edge_image_block, line_values, rc, rc_shape)

                # Get the sum of edge gradient
                #   magnitudes along the line.
                _get_sum1d_f(line_values, rc_shape, sums_array_)

                # Get the angle if there is a new maximum
                #   edge gradient magnitude.
                if sums_array_[0] > vars_array_[1]:

                    # Get the angle of the line.
                    theta_opt = _get_line_angle(rc[0, 0],
                                                rc[1, 0],
                                                rc[0, rc_shape-1],
                                                rc[1, rc_shape-1],
                                                window_size-1)

                    nc_opt = _orthogonal_opt(rc[0, 0], 
                                             rc[0, 0],
                                             rc[0, rc_shape-1],
                                             rc[1, rc_shape-1],
                                             center_value,
                                             half_window,
                                             window_size,
                                             edge_image_block,
                                             rc)

                    vars_array_[0] = theta_opt          # theta_opt
                    vars_array_[1] = sums_array_[0]     # si_opt
                    vars_array_[2] = sums_array_[1]     # n_opt
                    vars_array_[3] = nc_opt             # nc_opt
                    vars_array_[4] = pix_idx_r          # y endpoint
                    vars_array_[5] = end_idx_r          # x endpoint

            # print 'Indices: ', np.array(rc)
            # print 'Shape: ', rc_shape
            # print np.array(edge_image_block)
            # print 'Line values: ', np.array(line_values)
            # print 'Sums: ', np.array(sums_array_)
            # print 'Vars: ', np.array(vars_array_)
            # print 'Coords: ', rc[0, 0], rc[1, 0], rc[0, rc_shape-1], rc[1, rc_shape-1]
            # print
            # return

    # Iterate over top and bottom rows.
    for end_idx in range(0, 2):

        # Get the end index (0 or window size-1).
        end_idx_r = indices[end_idx]

        # Iterate over the window length.
        for pix_idx_r in range(0, window_size):

            # Ensure empty
            _fill_zeros(sums_array_, 2)

            with nogil:

                # Draw a line from the center pixel
                #   to the current end coordinate.
                draw_line(half_window, half_window, pix_idx_r, end_idx_r, rc)

                # Get the current line length.
                rc_shape = <int>rc[2, 0]

            # row of zeros, up to the line length
            line_values = rc[3, :rc_shape]

            with nogil:

                # Extract the values along the line.
                _extract_values(edge_image_block, line_values, rc, rc_shape)

                # Get the sum of edge gradient
                #   magnitudes along the line.
                _get_sum1d_f(line_values, rc_shape, sums_array_)

                # Get the angle if there is a new maximum
                #   edge gradient magnitude.
                if sums_array_[0] > vars_array_[1]:

                    # Get the angle of the line.
                    theta_opt = _get_line_angle(rc[0, 0],
                                                rc[1, 0],
                                                rc[0, rc_shape-1],
                                                rc[1, rc_shape-1],
                                                window_size-1)

                    nc_opt = _orthogonal_opt(rc[0, 0], rc[0, 0],
                                             rc[0, rc_shape-1],
                                             rc[1, rc_shape-1],
                                             center_value,
                                             half_window,
                                             window_size,
                                             edge_image_block,
                                             rc)

                    vars_array_[0] = theta_opt          # theta_opt
                    vars_array_[1] = sums_array_[0]     # si_opt
                    vars_array_[2] = sums_array_[1]     # n_opt
                    vars_array_[3] = nc_opt             # nc_opt
                    vars_array_[4] = pix_idx_r          # y endpoint
                    vars_array_[5] = end_idx_r          # x endpoint


cdef DTYPE_float32_t _edge_linearity(DTYPE_float32_t[:, :] optimal_values_array,
                                     DTYPE_float32_t y_endpoint,
                                     DTYPE_float32_t x_endpoint,
                                     int half_window,
                                     int window_size,
                                     DTYPE_float32_t param_l,
                                     DTYPE_float32_t theta_opt,
                                     DTYPE_float32_t[:, :] rc) nogil:

    cdef:
        Py_ssize_t coi
        int rc_shape
        # int iters = <int>((2. * param_l) + 1.)
        DTYPE_float32_t[:] line_values
        DTYPE_float32_t opt_val
        DTYPE_float32_t opt_max = -9999.

    if (y_endpoint < 0) or (x_endpoint < 0):
        return 0.

    # print 'rc:'
    # print np.array(rc)
    # print
    # print 'Line: ', half_window, y_endpoint, x_endpoint

    # Draw a line from the center to the endpoint,
    #   along the optimum angle.
    draw_line(half_window, half_window, <int>y_endpoint, <int>x_endpoint, rc)

    # Get the current line length.
    rc_shape = <int>rc[2, 0]

    # print 'Line shape: ', rc_shape

    # Row of zeros, up to the line length
    line_values = rc[3, :rc_shape]

    # print 'Line values: ', np.array(line_values)

    # Extract the values along the optimum angle.
    _extract_values(optimal_values_array, line_values, rc, rc_shape)

    # print 'Line values: ', np.array(line_values)
    # print 'Line shape: ', rc_shape
    # print

    # Get the absolute cosine summation
    #   along the optimum angle.
    for coi in range(1, rc_shape):

        if line_values[coi] > -9999:

            opt_val = _abs(cos(line_values[coi] - theta_opt))
            opt_max = _nogil_get_max(opt_max, opt_val)

        else:
            break

    if opt_max < 0:
        return 0.
    else:
        return opt_max #/ ((2.*param_l) + 1.)


cdef DTYPE_float32_t _edge_saliency(DTYPE_float32_t si_opt,
                                    DTYPE_float32_t n_opt,
                                    DTYPE_float32_t nc_opt) nogil:

    # si_opt * n_opt * nc_opt
    return si_opt * n_opt * nc_opt


cdef np.ndarray[DTYPE_float32_t, ndim=3] saliency_window(DTYPE_float32_t[:, :] edge_image, int window_size):

    """
    Computes image edge saliency
    """

    cdef:
        int rows = edge_image.shape[0]
        int cols = edge_image.shape[1]
        Py_ssize_t i, j
        int half_window = int(window_size / 2.)
        int row_dims = int(rows - (half_window * 2.))
        int col_dims = int(cols - (half_window * 2.))
        DTYPE_float32_t[:, :] out_array_sal = np.zeros((rows, cols), dtype='float32')
        DTYPE_float32_t[:, :] out_array_lin = np.zeros((rows, cols), dtype='float32')
        DTYPE_float32_t[:, :, :] out_array_vars = np.zeros((6, rows, cols), dtype='float32') - 9999.
        DTYPE_uint8_t[:] pix_indices = np.array([0, window_size-1], dtype='uint8')
        DTYPE_float32_t param_l = float(half_window + 1)
        DTYPE_float32_t param_v = (param_l / 2.) + 1.
        DTYPE_float32_t[:, :] rcc = np.zeros((4, window_size*2), dtype='float32')
        DTYPE_float32_t[:] sums_array = np.zeros(2, dtype='float32')
        DTYPE_float32_t theta_opt

        # The `vars_array` holds:
        #   0: theta_opt
        #   1: si_opt
        #   2: n_opt
        #   3: y (i) coordinate of `theta_opt` endpoint
        #   4: x (j) coordinate of `theta_opt` endpoint
        DTYPE_float32_t[:] vars_array = np.zeros(6, dtype='float32')

    #####################################
    # Edge orientation derivation (3.3.1)
    #####################################
    # It is necessary to iterate over the entire image
    #   before edge linearity and edge saliency because
    #   all of the optimum values need to be found.
    for i in range(0, row_dims):
        for j in range(0, col_dims):

            if edge_image[i+half_window, j+half_window] > 1:

                # First, get the ...
                #
                # theta_opt:
                #   optimal edge direction
                # si_opt:
                #   sum of EGM over the optimum line
                # n_opt:
                #   the number of pixels along the optimal line
                _optimal_edge_orientation(edge_image[i:i+window_size, j:j+window_size],
                                          pix_indices,
                                          half_window,
                                          window_size,
                                          rcc,
                                          vars_array,
                                          sums_array)

                out_array_vars[0, i+half_window, j+half_window] = vars_array[0]     # theta_opt
                out_array_vars[1, i+half_window, j+half_window] = vars_array[1]     # si_opt
                out_array_vars[2, i+half_window, j+half_window] = vars_array[2]     # n_opt
                out_array_vars[3, i+half_window, j+half_window] = vars_array[3]     # nc_opt
                out_array_vars[4, i+half_window, j+half_window] = vars_array[4]     # y endpoint
                out_array_vars[5, i+half_window, j+half_window] = vars_array[5]     # x endpoint


    ###################################
    # Edge linearity derivation (3.3.2)
    ###################################
    # TODO: collinearity
    with nogil:

        for i in range(0, row_dims):
            for j in range(0, col_dims):

                if out_array_vars[0, i+half_window, j+half_window] > -9999:

                    theta_opt = out_array_vars[0, i+half_window, j+half_window]

                    out_array_lin[i+half_window,
                                  j+half_window] = _edge_linearity(out_array_vars[0, i:i+window_size, j:j+window_size],
                                                                   out_array_vars[4, i+half_window, j+half_window],
                                                                   out_array_vars[5, i+half_window, j+half_window],
                                                                   half_window,
                                                                   window_size,
                                                                   param_l,
                                                                   theta_opt,
                                                                   rcc)

                else:
                    out_array_lin[i+half_window, j+half_window] = 0.

    ##################################
    # Edge saliency derivation (3.3.3)
    ##################################
    with nogil:

       for i in range(0, row_dims):
           for j in range(0, col_dims):

               if out_array_lin[i+half_window, j+half_window] > 0:

                   out_array_sal[i+half_window,
                                 j+half_window] = _edge_saliency(out_array_vars[1, i+half_window, j+half_window],
                                                                 out_array_vars[2, i+half_window, j+half_window],
                                                                 out_array_vars[3, i+half_window, j+half_window])

               else:
                   out_array_sal[i+half_window, j+half_window] = 0.

    return np.vstack((np.float32(out_array_lin), np.float32(out_array_sal))).reshape(2, rows, cols)


cdef DTYPE_uint8_t[:, :] _fill_circles(DTYPE_uint8_t[:, :] image_block, DTYPE_uint8_t[:, :] circle_block,
                                       DTYPE_intp_t dims, DTYPE_float32_t circle_match,
                                       DTYPE_intp_t[:] rr_, DTYPE_intp_t[:] cc_):

    cdef:
        Py_ssize_t i_, j_
        Py_ssize_t overlap_count = 0

    for i_ in xrange(0, dims):

        for j_ in xrange(0, dims):

            if (image_block[i_, j_] == 1) and (circle_block[i_, j_] == 1):
                overlap_count += 1

    if overlap_count >= circle_match:
        return fill_block(image_block, rr_, cc_, 1)
    else:
        return image_block


cdef tuple get_circle_locations(DTYPE_uint8_t[:, :] circle_block, int window_size):

    cdef:
        Py_ssize_t i_, j_
        Py_ssize_t counter = 0
        DTYPE_intp_t[:] rr = np.zeros(window_size*window_size, dtype='intp')
        DTYPE_intp_t[:] cc = rr.copy()

    for i_ in xrange(0, window_size):

        for j_ in xrange(0, window_size):

            if circle_block[i_, j_] == 1:

                rr[counter] = i_
                cc[counter] = j_

    return rr[:counter], cc[:counter]


cdef np.ndarray[DTYPE_uint8_t, ndim=2] fill_circles(DTYPE_uint8_t[:, :] image_array, list circle_list):

    """
    Fills circles
    """

    cdef:
        int rows = image_array.shape[0]
        int cols = image_array.shape[1]
        Py_ssize_t i, j, ci
        int half_window
        int n_circles = len(circle_list)
        DTYPE_intp_t window_size
        int row_dims
        int col_dims
        DTYPE_uint8_t[:, :] circle
        DTYPE_uint8_t circle_sum
        DTYPE_float32_t required_percent = .3
        DTYPE_float32_t circle_match
        DTYPE_intp_t[:] rr, cc

    for ci in xrange(0, n_circles):

        circle = circle_list[ci]

        window_size = circle.shape[0]

        half_window = int(window_size / 2)
        row_dims = rows - (half_window * 2)
        col_dims = cols - (half_window * 2)

        # Get the circle total
        circle_sum = _get_sum_uint8(circle, window_size, window_size)

        # Get the required percentage.
        circle_match = float(circle_sum) * required_percent

        rr, cc = get_circle_locations(circle, window_size)

        for i in xrange(0, row_dims):

            for j in xrange(0, col_dims):

                image_array[i:i+window_size, j:j+window_size] = _fill_circles(image_array[i:i+window_size,
                                                                                          j:j+window_size],
                                                                              circle,
                                                                              window_size,
                                                                              circle_match, rr, cc)

    return np.asarray(image_array).astype(np.uint8)


cdef np.ndarray[DTYPE_uint8_t, ndim=2] fill_window(DTYPE_uint8_t[:, :] image_array,
                                                   int window_size,
                                                   int n_neighbors):

    """
    Fills holes
    """

    cdef:
        int rows = image_array.shape[0]
        int cols = image_array.shape[1]
        Py_ssize_t i, j, ij
        int half_window = int(window_size / 2.)
        int row_dims = rows - (half_window*2)
        int col_dims = cols - (half_window*2)
        DTYPE_uint8_t[:] rr
        DTYPE_uint8_t[:] cc
        list idx_rr, idx_cc

    if n_neighbors == 4:

        rr = np.array([0, 1, 1, 2], dtype='uint8')
        cc = np.array([1, 0, 2, 1], dtype='uint8')

        with nogil:

            for i in range(0, row_dims):
                for j in range(0, col_dims):

                    image_array[i+half_window, j+half_window] = _fill_holes(image_array[i:i+window_size,
                                                                                        j:j+window_size],
                                                                            rr, cc, window_size, n_neighbors)

    elif n_neighbors == 2:

        idx_rr = [np.array([0, 2], dtype='uint8'),
                  np.array([1, 1], dtype='uint8')]

        idx_cc = [np.array([1, 1], dtype='uint8'),
                  np.array([0, 2], dtype='uint8')]

        for ij in range(0, 2):

            rr = idx_rr[ij]
            cc = idx_cc[ij]

            with nogil:

                for i in range(0, row_dims):
                    for j in range(0, col_dims):

                        image_array[i+half_window, j+half_window] = _fill_holes(image_array[i:i+window_size,
                                                                                            j:j+window_size],
                                                                                rr, cc, window_size, n_neighbors)

    return np.uint8(np.asarray(image_array))


cdef DTYPE_float32_t _inhibited_egm(DTYPE_float32_t[:, :] block,
                                    DTYPE_float32_t[:, :] circle_block,
                                    int window_size, int hw) nogil:

    cdef:
        Py_ssize_t ii, jj
        DTYPE_float32_t inhibition_term = 0.
        DTYPE_float32_t inside_term = 0.
        Py_ssize_t counter = 0
        Py_ssize_t counter_inside = 0

    # Get the weighted average within the local window.
    #   This is the inhibition term, T.
    for ii in range(0, window_size):

        for jj in range(0, window_size):

            if (ii != jj) and (circle_block[ii, jj] != 0):

                inhibition_term += block[ii, jj] * circle_block[ii, jj]
                counter += 1

            else:

                inside_term += block[ii, jj]
                counter_inside += 1

    inhibition_term /= counter
    inside_term /= counter_inside

    return block[hw, hw] - (inhibition_term / inside_term)


cdef np.ndarray[DTYPE_float32_t, ndim=2] _inhibition(DTYPE_float32_t[:, :] image_array,
                                                     DTYPE_intp_t window_size,
                                                     DTYPE_float32_t[:] inhibition_scales):

    """
    Local EGM inhibition

    References:
        Giuseppi Papari and Patrizio Campisi (2007). Multilevel surround inhibition:
            A biologically inspired contour detector.
    """

    cdef:
        Py_ssize_t i, j, si
        int rows = image_array.shape[0]
        int cols = image_array.shape[1]
        int half_window = int(window_size / 2)
        int row_dims = rows - (half_window*2)
        int col_dims = cols - (half_window*2)
        DTYPE_float32_t[:, :] circle_block
        DTYPE_float32_t[:, :] out_image = np.zeros((rows, cols), dtype='float32')
        # int n_scales = inhibition_scales.shape[0]

    if window_size == 3:

        circle_block = np.array([[0, 1, 0],
                                 [1, 0, 1],
                                 [0, 1, 0]], dtype='float32')

    elif window_size == 5:

        circle_block = np.array([[1., .75, 0, .75, 1.],
                                 [.75, .1, 0, .1, .75],
                                 [0, 0, 0, 0, 0],
                                 [.75, .1, 0, .1, .75],
                                 [1., .75, 0, .75, 1.]], dtype='float32')

    elif window_size == 7:

        circle_block = np.array([[0, 1, .75, 0, .75, 1, 0],
                                 [1, .5, .25, 0, .25, .5, 1],
                                 [.75, .25, .01, 0, .01, .25, .75],
                                 [.0, 0, 0, 0, 0, 0, 0],
                                 [.75, .25, .01, 0, .01, .25, .75],
                                 [1, .5, .25, 0, .25, .5, 1],
                                 [0, 1, .75, 0, .75, 1, 0]], dtype='float32')

    with nogil:

        # for si in range(0, n_scales):

        for i in range(0, row_dims):
            for j in range(0, col_dims):

                out_image[i+half_window, j+half_window] += _inhibited_egm(image_array[i:i+window_size, j:j+window_size],
                                                                          circle_block, window_size, half_window)

    return np.float32(out_image)# / float(n_scales)


cdef np.ndarray[DTYPE_float32_t, ndim=2] dist_window(DTYPE_float32_t[:, :] image_array,
                                                     DTYPE_intp_t window_size,
                                                     DTYPE_intp_t value_pos,
                                                     DTYPE_float32_t ignore_value,
                                                     DTYPE_float32_t[:, :] weights):

    """
    Computes focal (moving window) statistics.

    Args:
        image_array (ndarray): A nd ndarray, where the 1st array is the value array, and all other arrays
            are the distance arrays.
        window_size (Optional[int]): The window size. Default is 3.
        ignore_value (Optional[int or float]): A value to ignore in calculations. Default is None.
        resample (Optional[bool]): Whether to resample to the kernel size. Default is False.
        weights (Optional[ndarray]): Must match ``window_size`` x ``window_size``.
    """

    cdef:
        Py_ssize_t i, j
        int rows = image_array.shape[0]
        int cols = image_array.shape[1]
        int half_window = <int>(window_size / 2.)
        int row_dims = rows - (half_window*2)
        int col_dims = cols - (half_window*2)

        DTYPE_float32_t[:, ::1] out_array = np.zeros((rows, cols), dtype='float32')
        DTYPE_float32_t[:, ::1] dist_weights = np.array([[.7071, 1., .7071],
                                                         [1., 1., 1.],
                                                         [.7071, 1., .7071]], dtype='float32')

    with nogil:

        for i in range(0, row_dims):

            for j in range(0, col_dims):

                out_array[i+half_window, j+half_window] += _get_distance(image_array[i:i+window_size,
                                                                                     j:j+window_size],
                                                                         window_size,
                                                                         half_window,
                                                                         dist_weights,
                                                                         ignore_value)

    return np.float32(out_array)


cdef np.ndarray rgb_window(DTYPE_float32_t[:, :, :] image_array, unsigned int window_size):

    """
    Computes focal (moving window) statistics.

    Args:
        image_array (ndarray): A 2d ndarray of double (float64) precision.
        statistic (Optional[str]): The statistic to compute. Default is 'mean'.
            Choices are ['mean', 'min', 'max', 'median', 'majority', 'morph', 'percent', 'sum', 'distance'].
        window_size (Optional[int]): The window size. Default is 3.
        ignore_value (Optional[int or float]): A value to ignore in calculations. Default is None.
        resample (Optional[bool]): Whether to resample to the kernel size. Default is False.
        weights (Optional[ndarray]): Must match ``window_size`` x ``window_size``.
    """

    cdef:
        int dims = image_array.shape[0]
        int rows = image_array.shape[1]
        int cols = image_array.shape[2]
        Py_ssize_t i, j
        int half_window = int(window_size / 2)
        int row_dims = rows - (half_window*2)
        int col_dims = cols - (half_window*2)
        DTYPE_float32_t[:, :] out_array

    out_array = np.zeros((rows, cols), dtype='float32')

    for i in xrange(0, row_dims):

        for j in xrange(0, col_dims):

            out_array[i+half_window, j+half_window] = _get_distance_rgb(image_array[:, i:i+window_size, j:j+window_size],
                                                                        window_size, window_size, half_window, dims)

    return np.asarray(out_array).astype(np.float32)


cdef np.ndarray window(DTYPE_float32_t[:, ::1] image_array,
                       str statistic,
                       unsigned int window_size,
                       int target_value,
                       int ignore_value,
                       unsigned int iterations,
                       DTYPE_float32_t[:, ::1] weights,
                       unsigned int skip_block):

    """
    Computes focal (moving window) statistics.
    """

    cdef:
        Py_ssize_t i, j, iters, ic, jc
        unsigned int rows = image_array.shape[0]
        unsigned int cols = image_array.shape[1]
        unsigned int half_window = <int>(window_size / 2.)
        unsigned int row_dims = rows - (half_window*2)
        unsigned int col_dims = cols - (half_window*2)
        DTYPE_float32_t[:, ::1] out_array
        metric_ptr window_function

    if statistic == 'mean':
        window_function = &_get_mean
    elif statistic == 'min':
        window_function = &_get_min
    elif statistic == 'max':
        window_function = &_get_max
    # elif statistic == 'median':
    #     window_function = &_get_median
    # elif statistic == 'majority':
    #     window_function = &_get_majority
    elif statistic == 'percent':
        window_function = &_get_percent
    elif statistic == 'sum':
        window_function = &_get_sum
    # elif statistic == 'morph':
    #     window_function = &_morph_pass
    elif statistic == 'duda':
        window_function = &_duda_operator
    else:
        raise ValueError('\n{} is not a supported statistic.\n'.format(statistic))

    if statistic == 'majority':
        out_array = image_array.copy()
    else:

        if skip_block > 0:

            out_array = np.zeros((int(np.ceil(rows / float(skip_block))),
                                  int(np.ceil(cols / float(skip_block)))), dtype='float32')

        else:
            out_array = np.zeros((rows, cols), dtype='float32')

    with nogil:

        for iters in range(0, iterations):

            if skip_block > 0:

                ic = 0
                for i from 0 <= i < rows by skip_block:

                    jc = 0
                    for j from 0 <= j < cols by skip_block:

                        out_array[ic, jc] = window_function(image_array[i:i+skip_block, j:j+skip_block],
                                                            skip_block,
                                                            skip_block,
                                                            target_value,
                                                            ignore_value,
                                                            weights,
                                                            half_window)

                        jc += 1

                    ic += 1

            else:

                for i in range(0, row_dims):

                    for j in range(0, col_dims):

                        out_array[i+half_window, j+half_window] = window_function(image_array[i:i+window_size,
                                                                                              j:j+window_size],
                                                                                  window_size,
                                                                                  window_size,
                                                                                  target_value,
                                                                                  ignore_value,
                                                                                  weights,
                                                                                  half_window)

    return np.float32(out_array)


def moving_window(np.ndarray image_array,
                  str statistic='mean',
                  DTYPE_intp_t window_size=3,
                  int skip_block=0,
                  int target_value=-9999,
                  int ignore_value=-9999,
                  int iterations=1,
                  weights=None,
                  endpoint_image=None,
                  gradient_image=None,
                  n_neighbors=4,
                  list circle_list=[],
                  int min_egm=25,
                  int smallest_allowed_gap=3,
                  int medium_allowed_gap=7,
                  list inhibition_scales=[1., .75, .5, .25],
                  int value_pos=0):

    """
    Args:
        image_array (2d array): The image to process.
        statistic (Optional[str]): The statistic to apply. Default is 'mean'.
            Choices are ['mean', 'min', 'max', 'median', 'majority', 'percent', 'sum',
            'link', 'fill', 'circles', 'distance'. 'rgb_distance'].
        window_size (Optional[int]): The window size (of 1 side). Default is 3.
        skip_block (Optional[int]): A block size skip factor. Default is 0.
        target_value (Optional[int]): A value to target (i.e., only operate on this value).
            Default is -9999, or target all values.
        ignore_value (Optional[int]): A value to ignore in calculations. Default is -9999, or don't ignore any values.
        iterations (Optional[int]): The number of iterations to apply the filter. Default is 1.
        weights (Optional[bool]): A ``window_size`` x ``window_size`` array of weights. Default is None.
        endpoint_image (Optional[2d array]): The endpoint image with ``statistic``='link'. Default is None.
        gradient_image (Optional[2d array]): The edge gradient image with ``statistic``='link'. Default is None.
        n_neighbors (Optional[int]): The number of neighbors with ``statistic``='fill'. Default is 4.
            Choices are [2, 4].
        circle_list (Optional[list]: A list of circles. Default is [].

    Returns
    """

    if statistic not in ['mean', 'min', 'max', 'median', 'majority', 'percent', 'sum',
                         'link', 'fill', 'circles', 'distance', 'rgb_distance', 'inhibition',
                         'saliency', 'duda']:

        raise ValueError('The statistic {} is not an option.'.format(statistic))

    if not isinstance(weights, np.ndarray):
        weights = np.ones((window_size, window_size), dtype='float32')

    if not isinstance(endpoint_image, np.ndarray):
        endpoint_image = np.empty((2, 2), dtype='uint8')

    if not isinstance(gradient_image, np.ndarray):
        gradient_image = np.empty((2, 2), dtype='uint8')

    if statistic == 'link':

        return link_window(np.uint8(np.ascontiguousarray(image_array)), window_size,
                           np.uint8(np.ascontiguousarray(endpoint_image)),
                           np.uint8(np.ascontiguousarray(gradient_image)),
                           min_egm, smallest_allowed_gap, medium_allowed_gap)

    elif statistic == 'saliency':

        return saliency_window(np.float32(np.ascontiguousarray(image_array)), window_size)

    elif statistic == 'inhibition':

        return _inhibition(np.float32(np.ascontiguousarray(image_array)), window_size,
                           np.array(inhibition_scales, dtype='float32'))

    elif statistic == 'fill':

        return fill_window(np.uint8(np.ascontiguousarray(image_array)), window_size, n_neighbors)

    elif statistic == 'circles':

        return fill_circles(np.uint8(np.ascontiguousarray(image_array)), circle_list)

    elif statistic == 'distance':

        return dist_window(np.float32(np.ascontiguousarray(image_array)),
                           window_size,
                           value_pos,
                           float(ignore_value),
                           weights=np.float32(np.ascontiguousarray(weights)))

    elif statistic == 'rgb_distance':

        return rgb_window(np.float32(np.ascontiguousarray(image_array)), window_size)

    else:

        return window(np.float32(np.ascontiguousarray(image_array)),
                      statistic,
                      window_size,
                      target_value,
                      ignore_value,
                      iterations,
                      np.float32(np.ascontiguousarray(weights)),
                      skip_block)