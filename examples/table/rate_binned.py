#!/usr/bin/env python

# Copyright (C) Duncan Macleod (2014)
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

"""Plotting `EventTable` rate versus time for specific column bins

I would like to study the rate at which event triggers are generated by the
`ExcessPower` gravitational-wave burst detection algorithm, over a small
stretch of data, binned by various thresholds on signal-to-noise ratio (SNR).

The data from which these events were generated contain a simulated
gravitational-wave signal, or hardware injection, used to validate
the performance of the LIGO detectors and downstream data analysis procedures.
"""

__author__ = "Duncan Macleod <duncan.macleod@ligo.org>"
__currentmodule__ = 'gwpy.table'

# First, we import the `EventTable` object and read in a set of events from
# a LIGO_LW-format XML file containing a
# :class:`sngl_burst <glue.ligolw.lsctables.SnglBurstTable>` table
from gwpy.table import EventTable
events = EventTable.read('H1-LDAS_STRAIN-968654552-10.xml.gz',
                         tablename='sngl_burst', columns=['time', 'snr'])

# .. note::
#
#    Here we manually specify the `columns` to read in order to optimise
#    the `read()` operation to parse only the data we actually need.

# Now we can use the :meth:`~EventTable.binned_event_rates` method to
# calculate the event rate in a number of bins of SNR.
rates = events.binned_event_rates(1, 'snr', [2, 3, 5, 8], operator='>=',
                                  start=968654552, end=968654562)
# .. note::
#
#    The list `[2, 3, 5, 8]` and operator `>=` specifies SNR tresholds of
#    2, 3, 5, and 8.

# Finally, we can make a plot:
plot = rates.plot(label='name')
plot.set_xlim(968654552, 968654562)
plot.set_ylabel('Event rate [Hz]')
plot.set_title('LIGO Hanford Observatory event rate for HW100916')
plot.add_legend()
plot.show()
