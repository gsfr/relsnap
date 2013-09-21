#!/usr/bin/env python

# @author:    Gunnar Schaefer
# @copyright: Copyright (c) 2013 Gunnar Schaefer
# @license:   MIT License

"""
Create relatively-timed ZFS snapshots
"""

import sys
import logging
import argparse
import datetime
import subprocess


class Snapshot(object):

    def __init__(self, name, type_):
        self.name = name
        self.type_ = type_
        self.timestamp = datetime.datetime.strptime(self.name.split('@')[1], DFMT)

    def __repr__(self):
        return self.name


class SnapInterval(object):

    def __init__(self, type_, interval):
        self.type_ = type_
        self.interval = interval


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('operation', choices=['init', 'create', 'destroy'], help='operation to perform')
        self.add_argument('filesystem', help='ZFS file system to process')
        self.add_argument('-l', '--loglevel', default='info', help='log level (default: info)')
        self.add_argument('-p', '--prefix', default='relsnap', help='ZFS property prefix (default: relsnap)')
        self.add_argument('-c', '--count', type=int, default='8', help='desired snapshot count (default: 8)')


DFMT = '%Y-%m-%d-%H%M'
EPSILON = datetime.timedelta(minutes=1)
SNAP_INTERVALS = [
        SnapInterval('quarterly', datetime.timedelta(days=90)),
        SnapInterval('monthly', datetime.timedelta(days=30)),
        SnapInterval('weekly', datetime.timedelta(days=7)),
        SnapInterval('daily', datetime.timedelta(days=1)),
        SnapInterval('hourly', datetime.timedelta(hours=1)),
        ]


args = ArgumentParser().parse_args()
logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=getattr(logging, args.loglevel.upper())
        )

if args.operation == 'init':
    logging.info('initializing snapcnt properties on %s' % args.filesystem)
    for si in SNAP_INTERVALS:
        cmd = 'zfs set %s:snapcnt-%s=%d %s' % (args.prefix, si.type_, args.count, args.filesystem)
        logging.info(cmd)
        subprocess.check_output(cmd, shell=True)
    sys.exit()

now = datetime.datetime.now()
all_file_systems = subprocess.check_output('zfs list -H -o name -r %s' % args.filesystem, shell=True)
for file_system in all_file_systems.splitlines():
    logging.debug(file_system)
    all_fs_snaps = {}
    all_snapshots_out = subprocess.check_output('zfs list -H -d 1 -o name,%s:snaptype -t snapshot %s' % (args.prefix, file_system), shell=True)
    for line in all_snapshots_out.splitlines():
        snapshot = Snapshot(*line.split())
        all_fs_snaps[snapshot.type_] = all_fs_snaps.get(snapshot.type_, []) + [snapshot]
    for i, si in enumerate(SNAP_INTERVALS):
        snap_cnt = int(subprocess.check_output('zfs get -H -o value %s:snapcnt-%s %s' % (args.prefix, si.type_, file_system), shell=True))
        if args.operation == 'create':
            if snap_cnt > 0:
                ho_fs_snaps = sum([all_fs_snaps.get(ho_type, []) for ho_type in sum([[SNAP_INTERVALS[j].type_] for j in range(i+1)], [])], [])
                logging.debug('  ' + si.type_)
                logging.debug('    ' + ', '.join([snap.name.split('@')[1] for snap in ho_fs_snaps]))
                if not ho_fs_snaps or max([snap.timestamp for snap in ho_fs_snaps]) + si.interval - EPSILON <= now:
                    cmd = 'zfs snapshot -o %s:snaptype=%s %s@%s' % (args.prefix, si.type_, file_system, now.strftime(DFMT))
                    logging.debug(cmd)
                    subprocess.check_output(cmd, shell=True)
                    break
        else: # args.operation == 'destroy'
            for snapshot in all_fs_snaps.get(si.type_, [])[:-snap_cnt]:
                cmd = 'zfs destroy %s' % snapshot.name
                logging.debug(snapshot.type_ + ': ' + cmd)
                subprocess.check_output(cmd, shell=True)
