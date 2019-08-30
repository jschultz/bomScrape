#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2019 Jonathan Schultz
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
import argparse
import datetime
from dateutil import parser as dateparser
import sys
import os
import shutil
import csv
from matplotlib import pyplot

def plotAverageRainfall(arglist=None):

    parser = argparse.ArgumentParser(description='Sites BOM data.',
                                     fromfile_prefix_chars='@')

    parser.add_argument(      '--since',      type=str, help='Lower bound date/time in any sensible format')
    parser.add_argument(      '--until',      type=str, help='Upper bound date/time in any sensible format')

    parser.add_argument('-v', '--verbosity',  type=int, default=1)
    parser.add_argument('-l', '--limit',      type=int, help='Limit number of rows to process')

    parser.add_argument('--outfile',          type=str, help='Output image file')
    parser.add_argument('--logfile',          type=str, help='Log file to record plot, default is <outfile>.log')
    parser.add_argument('--no-comments',      action='store_true', help='Do not produce a comments logfile')

    parser.add_argument('infile',             type=str, help='Input CSV file')

    args = parser.parse_args(arglist)
    hiddenargs = ['verbosity', 'no_comments']

    # Read comments at start of infile.
    infile = open(args.infile, 'rU')
    incomments = ''
    while True:
        line = infile.readline().decode('utf8')
        if line[:1] == '#':
            incomments += line
        else:
            infieldnames = next(csv.reader([line]))
            break

    if not incomments:
        incomments = '#' * 80 + '\n'

    inreader=csv.DictReader(infile, fieldnames=infieldnames)

    if (not args.no_comments) and (args.outfile or args.logfile):

        comments = ((' ' + args.outfile + ' ') if args.outfile else '').center(80, '#') + '\n'
        comments += '# ' + os.path.basename(sys.argv[0]) + '\n'
        arglist = args.__dict__.keys()
        for arg in arglist:
            if arg not in hiddenargs:
                val = getattr(args, arg)
                if type(val) == str or type(val) == unicode:
                    comments += '#     --' + arg + '="' + val + '"\n'
                elif type(val) == bool:
                    if val:
                        comments += '#     --' + arg + '\n'
                elif type(val) == list:
                    for valitem in val:
                        if type(valitem) == str:
                            comments += '#     --' + arg + '="' + valitem + '"\n'
                        else:
                            comments += '#     --' + arg + '=' + str(valitem) + '\n'
                elif val is not None:
                    comments += '#     --' + arg + '=' + str(val) + '\n'

        logfilename = args.logfile if args.logfile else args.outfile.rsplit('.',1)[0] + '.log'
        logfile = open(logfilename, 'w')
        logfile.write(comments.encode('utf-8'))
        logfile.write(incomments)
        logfile.close()

    until = dateparser.parse(args.until).date() if args.until else None
    since = dateparser.parse(args.since).date() if args.since else None

    if args.verbosity >= 1:
        print("Loading CSV data.", file=sys.stderr)

    xaxis = []
    ydata = []
    for row in inreader:
        date = datetime.date(year=int(row['Year']), month=int(row['Month']), day=int(row['Day']))
        if until and date >= until:
            continue
        elif since and date < since:
            break

        delta = float(row['Delta'])

        xaxis = [date] + xaxis
        ydata = [delta] + ydata

    cumulative = 0
    cumulativedata = []
    for y in ydata:
        cumulative += y
        cumulativedata += [cumulative]

    fig, ax1 = pyplot.subplots()
    pyplot.title(args.infile)
    ax2 = ax1.twinx()
    ax1.plot(xaxis, ydata, color='blue')
    ax1.tick_params(axis='y', colors='blue')
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Difference from long-term average (mm)')
    ax2.fill_between(xaxis, cumulativedata, color='red')
    ax2.tick_params(axis='y', colors='red')
    ax2.set_ylabel('Cumulative difference from long-term average (mm)')


    def align_yaxis(ax1, ax2):
        """Align zeros of the two axes, zooming them out by same ratio"""
        axes = (ax1, ax2)
        extrema = [ax.get_ylim() for ax in axes]
        tops = [extr[1] / (extr[1] - extr[0]) for extr in extrema]
        # Ensure that plots (intervals) are ordered bottom to top:
        if tops[0] > tops[1]:
            axes, extrema, tops = [list(reversed(l)) for l in (axes, extrema, tops)]

        # How much would the plot overflow if we kept current zoom levels?
        tot_span = tops[1] + 1 - tops[0]

        b_new_t = extrema[0][0] + tot_span * (extrema[0][1] - extrema[0][0])
        t_new_b = extrema[1][1] - tot_span * (extrema[1][1] - extrema[1][0])
        axes[0].set_ylim(extrema[0][0], b_new_t)
        axes[1].set_ylim(t_new_b, extrema[1][1])

    align_yaxis(ax1, ax2)
    ax1.axhline(0)

    # http://matplotlib.1069221.n5.nabble.com/Control-twinx-series-zorder-ax2-series-behind-ax1-series-or-place-ax2-on-left-ax1-on-right-tp12994p12995.html
    ax1.set_zorder(ax2.get_zorder()+1)
    ax1.patch.set_visible(False)

    if args.outfile:
        pyplot.savefig(args.outfile)
    else:
        pyplot.show()

    exit(0)

if __name__ == '__main__':
    plotAverageRainfall(None)
