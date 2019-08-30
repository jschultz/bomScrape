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
import re
from matplotlib import pyplot, tri
import numpy

def contourRainfall(arglist=None):

    parser = argparse.ArgumentParser(description='Sites BOM data.',
                                     fromfile_prefix_chars='@')

    parser.add_argument('-v', '--verbosity',  type=int, default=1)
    parser.add_argument('-l', '--limit',      type=int, help='Limit number of rows to process')

    parser.add_argument('-f', '--filter',     type=str, help='Python expression evaluated to determine whether site is included')

    parser.add_argument(      '--since',      type=str, help='Start date to produce contour from')
    parser.add_argument(      '--until',      type=str, help='End date to produce contour from')

    parser.add_argument('--outfile',          type=str, help='Output image file')
    parser.add_argument('--logfile',          type=str, help='Log file to record plot, default is <outfile>.log')
    parser.add_argument('--no-comments',      action='store_true', help='Do not produce a comments logfile')

    parser.add_argument('infile',             type=str, help='Site CSV file')

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

    def clean(v):
        return re.sub('\W|^(?=\d)','_', v)

    if args.filter:
        if args.verbosity >= 2:
            print("\
def evalfilter(" + ','.join([clean(fieldname) for fieldname in infieldnames]) + ",**kwargs):\n\
    return " + args.filter, file=sys.stderr)
        exec("\
def evalfilter(" + ','.join([clean(fieldname) for fieldname in infieldnames]) + ",**kwargs):\n\
    return " + args.filter, globals())

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

    sites = []
    for row in inreader:
        keep = True
        if args.filter:
            rowargs = {clean(item[0]): item[1] for item in row.items()}
            if args.verbosity >= 2:
                print("evalfilter(" + repr(rowargs) + ")", file=sys.stderr)
            keep = evalfilter(**rowargs) or False
            if args.verbosity >= 2:
                print("    --> " + repr(keep), file=sys.stderr)
        if not keep:
            continue

        sites += [row]

    xdata = []
    ydata = []
    textdata = []
    zdata = []
    for site in sites:
        sitefilename = site['Name'] + '_delta.csv'
        if os.path.isfile(sitefilename):
            if args.verbosity >= 2:
                print("Opening site data file: " + sitefilename, file=sys.stderr)
            sitefile = open(sitefilename, 'r')
            zvalue = None
            for row in csv.DictReader(filter(lambda line: line[0]!='#', sitefile)):
                date = datetime.date(year=int(row['Year']), month=int(row['Month']), day=int(row['Day']))
                if until and date >= until:
                    continue
                elif since and date < since:
                    break

                zvalue = (zvalue or 0) + float(row['Delta'])

            if zvalue:
                if args.verbosity >= 2:
                    print("Adding data for site: " + site['Name'], file=sys.stderr)
                xdata += [float(site['Lon'])]
                ydata += [float(site['Lat'])]
                textdata += [site['Name']]
                zdata += [zvalue]

    xi = numpy.linspace(min(xdata), max(xdata), 100)
    yi = numpy.linspace(min(ydata), max(ydata), 100)

    triang = tri.Triangulation(xdata, ydata)
    interpolator = tri.LinearTriInterpolator(triang, zdata)
    Xi, Yi = numpy.meshgrid(xi, yi)
    zi = interpolator(Xi, Yi)

    fig, ax1 = pyplot.subplots(figsize=(16, 8))
    pyplot.title("Cumulative rainfall compared with average: " + args.since or "" + " to " + args.until or "")
    ax1.contour(xi, yi, zi, linewidths=0.5, colors="k")
    cntr1 = ax1.contourf(xi, yi, zi, 10, cmap="hot")
    fig.colorbar(cntr1, ax=ax1)
    ax1.plot(xdata, ydata, 'ko', ms=3)
    for i, text in enumerate(textdata):
        ax1.annotate(text, (xdata[i], ydata[i]))
    if args.outfile:
        pyplot.savefig(args.outfile)
    else:
        pyplot.show()

    exit(0)

if __name__ == '__main__':
    contourRainfall(None)
