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

from argrecord import ArgumentHelper, ArgumentRecorder
import requests
import re
from dateutil import parser as dateparser
from datetime import datetime
import sys
import os
import shutil
import csv
import string
from sqlalchemy import *
from sqlalchemy import exc

def bomSites(arglist=None):

    parser = ArgumentRecorder(description='Output BOM site data for a given state to CSV or database.',
                              fromfile_prefix_chars='@')

    parser.add_argument('-v', '--verbosity',  type=int, default=1, private=True)
    parser.add_argument('-l', '--limit',      type=int, help='Limit number of rows to process')

    parser.add_argument('-s', '--state',      type=str, choices=['SA', 'NSW', 'NT', 'QLD', 'TAS', 'VIC', 'WA'], required=True)

    parser.add_argument('--no-comments',      action='store_true', help='Do not output descriptive comments')
    parser.add_argument('--no-header',        action='store_true', help='Do not output CSV header with column names')

    parser.add_argument('outdata',            type=str, nargs='?', help='Output CSV file or SQLAlchemy specification, otherwise use stdout.', output=True)

    args = parser.parse_args(arglist)

    if not args.outdata:
        outfile = sys.stdout
        bomdb = None
        logfilename = None
    elif "://" in args.outdata:    # Database
        outfile = None
        bomdb = create_engine(args.outdata)
        logfilename = args.outdata.split('/')[-1].rsplit('.',1)[0] + '.log'
    else:
        if os.path.exists(args.outdata):
            shutil.move(args.outdata, args.outdata + '.bak')

        outfile = open(args.outdata, 'w')
        bomdb = None
        logfilename = None

    if not args.no_comments:
        if logfilename:
            logfile = open(logfilename, 'w')
        else:
            logfile = outfile

        parser.write_comments(args, logfile, incomments=ArgumentHelper.separator())

        if logfilename:
            logfile.close()

    if args.verbosity >= 1:
        print("Loading BOM data.", file=sys.stderr)

    reqlines = requests.get('http://www.bom.gov.au/climate/data/lists_by_element/alpha' + args.state + '_136.txt', stream=True).iter_lines(decode_unicode=True)

    firstline = next(reqlines)
    produced = dateparser.parse(re.match('.+Produced: (.+)', firstline).group(1))

    dummyline   = next(reqlines)
    headingline = next(reqlines)
    fields = [(m.group(), m.start()) for m in re.finditer(r'\S+', headingline)]
    for idx in range(len(fields)):
        if idx:
            fields[idx-1] += (fields[idx][1] - 1,)
    fields[-1] += (None,)
    dummyline   = next(reqlines)

    def str2bool(v):
        return v.lower() in ("yes", "true", "t", "1")

    def partdate(v):
        return dateparser.parse(v, default=datetime(1,1,1))

    fieldtype = {
        'Site':  ('Site',    Integer,    int),
        'Name':  ('Name',    String(32), str.strip),
        'Lat':   ('Lat',     Float,      float),
        'Lon':   ('Lon',     Float,      float),
        'Start': ('Start',   Date,       partdate),
        'End':   ('End',     Date,       partdate),
        'Years': ('Years',   Float,      float),
        '%':     ('Percent', Integer,    int),
        'AWS':   ('AWS',     Boolean,    str2bool)
    }

    if bomdb:    # Database
        bomcon = bomdb.connect()
        bomtr = bomcon.begin()
        bommd = MetaData(bind=bomdb)
        try:
            bomSite = Table('Site', bommd, autoload=True)
        except exc.NoSuchTableError:
            bomSite = Table('Site', bommd)
            for field in fields:
                bomSite = Table('Site', bommd,
                                Column(fieldtype[field[0]][0], fieldtype[field[0]][1]), extend_existing=True)
            bomSite.create(bomdb)

        inrowcount = 0
        while True:
            if args.limit and inrowcount == args.limit:
                break
            inrowcount += 1

            line = next(reqlines)
            if not line:
                break
            bomcon.execute(bomSite.insert().values(
                { fieldtype[field[0]][0]: fieldtype[field[0]][2](line[field[1]:field[2]]) for field in fields }))

        bomtr.commit()
        bomtr = None
        bomcon.close()
        bomdb.dispose()

    else:
        outcsv=csv.writer(outfile)
        if not args.no_header:
            outcsv.writerow([fieldtype[field[0]][0] for field in fields])
        inrowcount = 0
        while True:
            if args.limit and inrowcount == args.limit:
                break
            inrowcount += 1

            line = next(reqlines)
            if not line:
                break
            outcsv.writerow([str.strip(line[field[1]:field[2]]) for field in fields])

        outfile.close()

    exit(0)

if __name__ == '__main__':
    bomSites(None)
