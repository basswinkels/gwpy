# -*- coding: utf-8 -*-
# Copyright (C) Duncan Macleod (2018)
#
# This file is part of GWpy.
#
# GWpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GWpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GWpy.  If not, see <http://www.gnu.org/licenses/>.

"""Extension of `~matplotlib.axes.Axes` for gwpy
"""

from functools import wraps
from math import log
from numbers import Number

import numpy

from astropy.time import Time

from matplotlib import (__version__ as mpl_version, rcParams)
from matplotlib.artist import allow_rasterization
from matplotlib.axes import Axes as _Axes
from matplotlib.cbook import iterable
from matplotlib.collections import PolyCollection
from matplotlib.projections import register_projection
try:
    from matplotlib.axes._base import _process_plot_var_args
except ImportError:  # matplotlib-1.x
    from matplotlib.axes import _process_plot_var_args

from . import (Plot, colorbar as gcbar)
from .colors import format_norm
from ..time import (LIGOTimeGPS, to_gps)
from ..types import (Series, Array2D)
from .gps import GPS_SCALES

__author__ = 'Duncan Macleod <duncan.macleod@ligo.org>'

DEFAULT_SCATTER_COLOR = 'b' if mpl_version < '2.0' else None


def log_norm(func):
    """Wrap ``func`` to handle custom gwpy keywords for a LogNorm colouring
    """
    def decorated_func(*args, **kwargs):
        norm, kwargs = format_norm(kwargs)
        kwargs['norm'] = norm
        return func(*args, **kwargs)
    return decorated_func


def xlim_as_gps(func):
    """Wrap ``func`` to handle pass limit inputs through `gwpy.time.to_gps`
    """
    @wraps(func)
    def wrapped_func(self, left=None, right=None, **kw):
        if right is None and iterable(left):
            left, right = left
        kw['left'] = left
        kw['right'] = right
        gpsscale = self.get_xscale() in GPS_SCALES
        for key in ('left', 'right'):
            if gpsscale:
                try:
                    kw[key] = numpy.longdouble(str(to_gps(kw[key])))
                except TypeError:
                    pass
        return func(self, **kw)
    return wrapped_func


# -- new Axes -----------------------------------------------------------------

class Axes(_Axes):
    def __init__(self, *args, **kwargs):
        super(Axes, self).__init__(*args, **kwargs)

        # handle Series in `ax.plot()`
        self._get_lines = PlotArgsProcessor(self)

        # reset data formatters (for interactive plots) to support
        # GPS time display
        self.fmt_xdata = self._fmt_xdata
        self.fmt_ydata = self._fmt_ydata

    @allow_rasterization
    def draw(self, *args, **kwargs):
        labels = {}

        for ax in (self.xaxis, self.yaxis):
            if ax.get_scale() in GPS_SCALES and ax.isDefault_label:
                labels[ax] = ax.get_label_text()
                trans = ax.get_transform()
                epoch = float(trans.get_epoch())
                unit = trans.get_unit_name()
                iso = Time(epoch, format='gps', scale='utc').iso
                utc = iso.rstrip('0').rstrip('.')
                ax.set_label_text('Time [{0!s}] from {1!s} UTC ({2!r})'.format(
                    unit, utc, epoch))

        try:
            super(Axes, self).draw(*args, **kwargs)
        finally:
            for ax in labels:  # reset labels
                ax.isDefault_label = True

    # -- auto-gps helpers -----------------------

    def _fmt_xdata(self, x):
        if self.get_xscale() in GPS_SCALES:
            return str(LIGOTimeGPS(x))
        raise TypeError  # fall back to default

    def _fmt_ydata(self, y):
        if self.get_yscale() in GPS_SCALES:
            return str(LIGOTimeGPS(y))
        raise TypeError  # fall back to default

    set_xlim = xlim_as_gps(_Axes.set_xlim)

    def set_epoch(self, epoch):
        """Set the epoch for the current GPS scale.

        This method will fail if the current X-axis scale isn't one of
        the GPS scales. See :ref:`gwpy-plot-gps` for more details.

        Parameters
        ----------
        epoch : `float`, `str`
            GPS-compatible time or date object, anything parseable by
            :func:`~gwpy.time.to_gps` is fine.
        """
        scale = self.get_xscale()
        return self.set_xscale(scale, epoch=epoch)

    def get_epoch(self):
        """Return the epoch for the current GPS scale/

        This method will fail if the current X-axis scale isn't one of
        the GPS scales. See :ref:`gwpy-plot-gps` for more details.
        """
        return self.get_xaxis().get_transform().get_epoch()

    # -- overloaded plotting methods ------------

    def scatter(self, x, y, c=DEFAULT_SCATTER_COLOR, **kwargs):
        # scatter with auto-sorting by colour
        if c is None and mpl_version < '2.0':
            c = DEFAULT_SCATTER_COLOR
        try:
            if c is None:
                raise ValueError
            c_array = numpy.asanyarray(c, dtype=float)
        except ValueError:  # no colour array
            pass
        else:
            c_sort = kwargs.pop('c_sort', True)
            if c_sort:
                sortidx = c_array.argsort()
                x = numpy.asarray(x)[sortidx]
                y = numpy.asarray(y)[sortidx]
                c = numpy.asarray(c)[sortidx]

        return super(Axes, self).scatter(x, y, c=c, **kwargs)

    scatter.__doc__ = _Axes.scatter.__doc__.replace(
        'marker :',
        'c_sort : `bool`, optional, default: True\n'
        '    Sort scatter points by `c` array value, if given.\n\n'
        'marker :',
    )

    @log_norm
    def imshow(self, array, **kwargs):
        if isinstance(array, Array2D):
            return self._imshow_array2d(array, **kwargs)

        image = super(Axes, self).imshow(array, **kwargs)
        self.autoscale(enable=None, axis='both', tight=None)
        return image

    imshow.__doc__ = _Axes.imshow.__doc__

    def _imshow_array2d(self, array, origin='lower', interpolation='none',
                        aspect='auto', **kwargs):
        """Render an `~gwpy.types.Array2D` using `Axes.imshow`
        """
        # calculate extent
        extent = tuple(array.xspan) + tuple(array.yspan)
        if self.get_xscale() == 'log' and extent[0] == 0.:
            extent = (1e-300,) + extent[1:]
        if self.get_yscale() == 'log' and extent[2] == 0.:
            extent = extent[:2] + (1e-300,) + extent[3:]
        kwargs.setdefault('extent', extent)

        return self.imshow(array.value.T, origin=origin, aspect=aspect,
                           interpolation=interpolation, **kwargs)

    @log_norm
    def pcolormesh(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], Array2D):
            return self._pcolormesh_array2d(*args, **kwargs)
        return super(Axes, self).pcolormesh(*args, **kwargs)

    pcolormesh.__doc__ = _Axes.pcolormesh.__doc__

    def _pcolormesh_array2d(self, array, **kwargs):
        """Render an `~gwpy.types.Array2D` using `Axes.pcolormesh`
        """
        x = numpy.concatenate((array.xindex.value, array.xspan[-1:]))
        y = numpy.concatenate((array.yindex.value, array.yspan[-1:]))
        xcoord, ycoord = numpy.meshgrid(x, y, copy=False, sparse=True)
        return self.pcolormesh(xcoord, ycoord, array.value.T, **kwargs)

    def hist(self, x, *args, **kwargs):
        x = numpy.asarray(x)

        # re-format weights as array if given as float
        weights = kwargs.get('weights', None)
        if isinstance(weights, Number):
            kwargs['weights'] = numpy.ones_like(x) * weights

        # calculate log-spaced bins on-the-fly
        if (kwargs.pop('logbins', False) and
                not iterable(kwargs.get('bins', None))):
            nbins = kwargs.get('bins', None) or rcParams.get('hist.bins', 30)
            # get range
            hrange = kwargs.pop('range', None)
            if hrange is None:
                try:
                    hrange = numpy.min(x), numpy.max(x)
                except ValueError as exc:
                    if str(exc).startswith('zero-size array'):  # no data
                        exc.args = ('cannot generate log-spaced histogram '
                                    'bins for zero-size array, '
                                    'please pass `bins` or `range` manually',)
                    raise
            # log-scale the axis and extract the base
            if kwargs.get('orientation') == 'horizontal':
                self.set_yscale('log', nonposy='clip')
                logbase = self.yaxis._scale.base
            else:
                self.set_xscale('log', nonposx='clip')
                logbase = self.xaxis._scale.base
            # generate the bins
            kwargs['bins'] = numpy.logspace(
                log(hrange[0], logbase), log(hrange[1], logbase),
                nbins+1, endpoint=True)

        return super(Axes, self).hist(x, *args, **kwargs)

    hist.__doc__ = _Axes.hist.__doc__.replace(
        'color :',
        'logbins : boolean, optional\n'
        '    If ``True``, use logarithmically-spaced histogram bins.\n\n'
        '    Default is ``False``\n\n'
        'color :')

    # -- new plotting methods -------------------

    def plot_mmm(self, data, lower=None, upper=None, **kwargs):
        """Plot a `Series` as a line, with a shaded region around it.

        The ``data`` `Series` is drawn, while the ``lower`` and ``upper``
        `Series` are plotted lightly below and above, with a fill
        between them and the ``data``.

        All three `Series` should have the same `~Series.index` array.

        Parameters
        ----------
        data : `~gwpy.types.Series`
            Data to plot normally.

        lower : `~gwpy.types.Series`
            Lower boundary (on Y-axis) for shade.

        upper : `~gwpy.types.Series`
            Upper boundary (on Y-axis) for shade.

        **kwargs
            Any other keyword arguments acceptable for
            :meth:`~matplotlib.Axes.plot`.

        Returns
        -------
        artists : `tuple`
            All of the drawn artists:

            - `~matplotlib.lines.Line2d` for ``data``,
            - `~matplotlib.lines.Line2D` for ``lower``, if given
            - `~matplotlib.lines.Line2D` for ``upper``, if given
            - `~matplitlib.collections.PolyCollection` for shading

        See Also
        --------
        matplotlib.axes.Axes.plot
            for a full description of acceptable ``*args`` and ``**kwargs``
        """
        alpha = kwargs.pop('alpha', .1)

        # plot mean
        line, = self.plot(data, **kwargs)
        out = [line]

        # modify keywords for shading
        kwargs.update({
            'label': '',
            'linewidth': line.get_linewidth() / 2,
            'color': line.get_color(),
            'alpha': alpha * 2,
        })

        # plot lower and upper Series
        fill = [data.xindex.value, data.value, data.value]
        for i, bound in enumerate((lower, upper)):
            if bound is not None:
                out.extend(self.plot(bound, **kwargs))
                fill[i+1] = bound.value

        # fill between
        out.append(self.fill_between(
            *fill, alpha=alpha, color=kwargs['color'],
            rasterized=kwargs.get('rasterized', True)))

        return out

    def tile(self, x, y, w, h, color=None,
             anchor='center', edgecolors='face', linewidth=0.8,
             **kwargs):
        """Plot rectanguler tiles based onto these `Axes`.

        ``x`` and ``y`` give the anchor point for each tile, with
        ``w`` and ``h`` giving the extent in the X and Y axis respectively.

        Parameters
        ----------
        x, y, w, h : `array_like`, shape (n, )
            Input data

        color : `array_like`, shape (n, )
            Array of amplitudes for tile color

        anchor : `str`, optional
            Anchor point for tiles relative to ``(x, y)`` coordinates, one of

            - ``'center'`` - center tile on ``(x, y)``
            - ``'ll'`` - ``(x, y)`` defines lower-left corner of tile
            - ``'lr'`` - ``(x, y)`` defines lower-right corner of tile
            - ``'ul'`` - ``(x, y)`` defines upper-left corner of tile
            - ``'ur'`` - ``(x, y)`` defines upper-right corner of tile

        **kwargs
            Other keywords are passed to
            :meth:`~matplotlib.collections.PolyCollection`

        Returns
        -------
        collection : `~matplotlib.collections.PolyCollection`
            the collection of tiles drawn

        Examples
        --------
        >>> import numpy
        >>> from matplotlib import pyplot
        >>> import gwpy.plot  # to get gwpy's Axes

        >>> x = numpy.arange(10)
        >>> y = numpy.arange(x.size)
        >>> w = numpy.ones_like(x) * .8
        >>> h = numpy.ones_like(x) * .8

        >>> fig = pyplot.figure()
        >>> ax = fig.gca()
        >>> ax.tile(x, y, w, h, anchor='ll')
        >>> pyplot.show()
        """
        # get color and sort
        if color is not None and kwargs.get('c_sort', True):
            sortidx = color.argsort()
            x = x[sortidx]
            y = y[sortidx]
            w = w[sortidx]
            h = h[sortidx]
            color = color[sortidx]

        # define how to make a polygon for each tile
        if anchor == 'll':
            def _poly(x, y, w, h):
                return ((x, y), (x, y+h), (x+w, y+h), (x+w, y))
        elif anchor == 'lr':
            def _poly(x, y, w, h):
                return ((x-w, y), (x-w, y+h), (x, y+h), (x, y))
        elif anchor == 'ul':
            def _poly(x, y, w, h):
                return ((x, y-h), (x, y), (x+w, y), (x+w, y-h))
        elif anchor == 'ur':
            def _poly(x, y, w, h):
                return ((x-w, y-h), (x-w, y), (x, y), (x, y-h))
        elif anchor == 'center':
            def _poly(x, y, w, h):
                return ((x-w/2., y-h/2.), (x-w/2., y+h/2.),
                        (x+w/2., y+h/2.), (x+w/2., y-h/2.))
        else:
            raise ValueError("Unrecognised tile anchor {!r}".format(anchor))

        # build collection
        cmap = kwargs.pop('cmap', rcParams['image.cmap'])
        coll = PolyCollection((_poly(*tile) for tile in zip(x, y, w, h)),
                              edgecolors=edgecolors, linewidth=linewidth,
                              **kwargs)
        if color is not None:
            coll.set_array(color)
            coll.set_cmap(cmap)

        out = self.add_collection(coll)
        self.autoscale_view()
        return out

    # -- overloaded auxiliary methods -----------

    def legend(self, *args, **kwargs):
        alpha = kwargs.pop("alpha", 0.8)
        linewidth = kwargs.pop("linewidth", 8)

        # make legend
        legend = super(Axes, self).legend(*args, **kwargs)

        # update alpha and linewidth for legend elements
        if legend is not None:
            lframe = legend.get_frame()
            lframe.set_alpha(alpha)
            lframe.set_linewidth(rcParams['axes.linewidth'])
            for line in legend.get_lines():
                line.set_linewidth(linewidth)

        return legend

    legend.__doc__ = _Axes.legend.__doc__

    def colorbar(self, mappable=None, **kwargs):
        """Add a `~matplotlib.colorbar.Colorbar` to these `Axes`

        Parameters
        ----------
        mappable : matplotlib data collection, optional
            collection against which to map the colouring, default will
            be the last added mappable artist (collection or image)

        fraction : `float`, optional
            fraction of space to steal from these `Axes` to make space
            for the new axes, default is ``0.`` if ``use_axesgrid=True``
            is given (default), otherwise default is ``.15`` to match
            the upstream matplotlib default.

        **kwargs
            other keyword arguments to be passed to the
            :meth:`Plot.colorbar` generator

        Returns
        -------
        cbar : `~matplotlib.colorbar.Colorbar`
            the newly added `Colorbar`

        See Also
        --------
        Plot.colorbar
        """
        fig = self.get_figure()
        if kwargs.get('use_axesgrid', True):
            kwargs.setdefault('fraction', 0.)
        if kwargs.get('fraction', 0.) == 0.:
            kwargs.setdefault('use_axesgrid', True)
        mappable, kwargs = gcbar.process_colorbar_kwargs(
            fig, mappable=mappable, ax=self, **kwargs)
        if isinstance(fig, Plot):
            # either we have created colorbar Axes using axesgrid1, or
            # the user already gave use_axesgrid=False, so we forcefully
            # disable axesgrid here in case fraction == 0., which causes
            # gridspec colorbars to fail.
            kwargs['use_axesgrid'] = False
        return fig.colorbar(mappable, **kwargs)


# override default Axes with this one by registering a projection with the
# same name

register_projection(Axes)


# -- overload Axes.plot() to handle Series ------------------------------------

class PlotArgsProcessor(_process_plot_var_args):
    """This class controls how ax.plot() works
    """
    def _grab_next_args(self, *args, **kwargs):
        """Find `Series` data in `plot()` args and unwrap
        """
        newargs = type(args)()
        for arg in args:
            if isinstance(arg, Series) and arg.ndim == 1:
                newargs += (arg.xindex.value, arg.value)
            else:
                newargs += (arg,)
        return super(PlotArgsProcessor, self)._grab_next_args(
            *newargs, **kwargs)
