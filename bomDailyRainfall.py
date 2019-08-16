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
import requests
import re
from dateutil import parser as dateparser

import sys
import os
import shutil
import csv
import string
from bs4 import BeautifulSoup
from StringIO import StringIO
from zipfile import ZipFile

from collections import OrderedDict
import itertools

from sqlalchemy import *
from sqlalchemy import exc

def bomScrape(arglist=None):

    parser = argparse.ArgumentParser(description='Scrape BOM data.',
                                     fromfile_prefix_chars='@')

    parser.add_argument('-v', '--verbosity',  type=int, default=1)
    parser.add_argument('-l', '--limit',      type=int, help='Limit number of rows to process')

    parser.add_argument('--no-comments',      action='store_true', help='Do not output descriptive comments')
    parser.add_argument('--no-header',        action='store_true', help='Do not output CSV header with column names')

    parser.add_argument('-f', '--filter',     type=str, help='Python expression evaluated to determine whether site is included')
    parser.add_argument('-d', '--dry-run',    action='store_true', help='Just select sites without collecting data')

    parser.add_argument('outdata',            type=str, nargs='?', help='Output CSV file or SQLAlchemy specification, otherwise use stdout.')

    args = parser.parse_args(arglist)
    hiddenargs = ['verbosity', 'no_comments']

    if not args.outdata:
        outfile = sys.stdout
        bomdb = None
        logfilename = None
    elif "://" in args.outdata:    # Database
        outfile = None
        bomdb = create_engine(args.outdata)
        bomcon = bomdb.connect()
        bommd = MetaData(bind=bomdb)
        logfilename = args.outdata.split('/')[-1].rsplit('.',1)[0] + '.log'
    else:
        if os.path.exists(args.outdata):
            shutil.move(args.outdata, args.outdata + '.bak')

        outfile = open(args.outdata, 'w')
        bomdb = None
        logfilename = None

    if not args.no_comments and not args.dry_run:

        comments = ((' ' + args.outdata + ' ') if args.outdata else '').center(80, '#') + '\n'
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

        incomments = ''
        if logfilename:
            if os.path.isfile(logfilename):
                incomments = open(logfilename, 'r').read()

            logfile = open(logfilename, 'w')
        else:
            logfile = outfile

        logfile.write(comments.encode('utf8'))
        logfile.write(incomments)

        if logfilename:
            logfile.close()



    bomSite = Table('Site', bommd, autoload=True)

    if args.filter:
            exec("\
def evalfilter(" + ','.join([col.key for col in bomSite.c]) + ",**kwargs):\n\
    return " + args.filter, globals())

    sites = []
    for row in bomcon.execute(bomSite.select()):
        rowargs = {item[0]: item[1] for item in row.items()}
        keep = True
        if args.filter:
            keep = evalfilter(**rowargs) or False
        if not keep:
            continue

        sites += [row]

    if args.verbosity >= 1:
        print ("Found " + str(len(sites)) + " sites:", file=sys.stderr)
        for site in sites:
            print("    " + site['Name'] + " - " + str(site['Site']), file=sys.stderr)

    for site in sites:

        if args.verbosity >= 1:
            print("Loading BOM daily rainfall data from site " + site['Name'] + " - " + str(site['Site']), file=sys.stderr)

        if args.dry_run:
            continue

        sitepage = requests.get('http://www.bom.gov.au/jsp/ncc/cdio/weatherData/av?p_nccObsCode=136&p_display_type=dailyDataFile&p_startYear=&p_c=&p_stn_num=' + str(site['Site']))

        soup = BeautifulSoup(sitepage.content, "html.parser")
        link = soup.find("a", title="Data file for daily rainfall data for all years")
        if not link:
            raise RuntimeError("Station data not found")

        zipfile = ZipFile(StringIO(requests.get('http://www.bom.gov.au' + link['href'], stream=True).content))
        csvname = next(name for name in zipfile.namelist() if name[-4:] == '.csv')
        csvdata = csv.DictReader(zipfile.open(csvname))
        fields = csvdata.fieldnames
        fields += ('Date',)

        def intOrNone(v):
            return int(v) if v else None

        def floatOrNone(v):
            return float(v) if v else None

        outfields = OrderedDict([
            ('Product code',                                    ('Product',     string.strip)),
            ('Bureau of Meteorology station number',            ('Site',        int)),
            ('Date',                                            ('Date',        dateparser.parse)),
            ('Rainfall amount (millimetres)',                   ('Rainfall',    floatOrNone)),
            ('Period over which rainfall was measured (days)',  ('Period',      intOrNone)),
            ('Quality',                                         ('Quality',     string.strip))])

        if bomdb:    # Database

            try:
                bomRainfall = Table('Rainfall', bommd, autoload=True)
            except exc.NoSuchTableError:
                bomRainfall = Table('Rainfall', bommd,
                                    Column('Product',   String(32), primary_key=True),
                                    Column('Site',      Integer,    primary_key=True),
                                    Column('Date',      Date,       primary_key=True),
                                    Column('Rainfall',  Float),
                                    Column('Period',    Integer),
                                    Column('Quality',   String(32)))
                bomRainfall.create(bomdb)

            bomtr = bomcon.begin()

            inrowcount = 0
            while True:
                if args.limit and inrowcount == args.limit:
                    break

                try:
                    line = csvdata.next()
                except StopIteration:
                    break
                if line['Rainfall amount (millimetres)'] == '':
                    continue

                inrowcount += 1

                line['Date'] = line['Year'] + '-' + line['Month'] + '-' + line['Day']

                try:
                    bomcon.execute(bomRainfall.insert().values(
                        { data[0]: data[1](line[field]) for field, data in outfields.items() }))
                except exc.IntegrityError:
                    bomcon.execute(bomRainfall.update(and_(
                        bomRainfall.c['Product'] == bindparam('Product'),
                        bomRainfall.c['Site']    == bindparam('Site'),
                        bomRainfall.c['Date']    == bindparam('Date'))).values(
                        { data[0]: bindparam(data[0]) for field, data in outfields.items() }),
                        { data[0]: data[1](line[field]) for field, data in outfields.items() })

            bomtr.commit()
            bomtr = None
        else:
            outcsv=csv.writer(outfile)
            if not args.no_header:
                outcsv.writerow([field for field in outfields ])

            inrowcount = 0
            while True:
                if args.limit and inrowcount == args.limit:
                    break

                try:
                    line = csvdata.next()
                except StopIteration:
                    break
                if line['Rainfall amount (millimetres)'] == '':
                    continue

                inrowcount += 1

                line['Date'] = line['Year'] + '-' + line['Month'] + '-' + line['Day']
                outcsv.writerow([line[field] for field in outfields])

    if bomdb:    # Database
        bomcon.close()
        bomdb.dispose()
    elif (args.outdata):
        outfile.close()

    exit(0)

if __name__ == '__main__':
    bomScrape(None)
