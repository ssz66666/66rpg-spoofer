#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import urllib.request as rq
import urllib.parse as urlp
import shutil
import os, sys
import pathlib
import concurrent.futures
import hashlib
import struct
import argparse

def md5_checksum_hex(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def generate_manifest(root):
    rootpath = pathlib.Path(root)
    folders = ["audio", "data", "font", "graphics"]
    items = []
    for dir in folders:
        for rt, _, files in os.walk(rootpath / dir):
            for f in files:
                fpath = pathlib.Path(rt, f)
                items.append([str(pathlib.PurePosixPath(fpath.relative_to(rootpath))), os.path.getsize(fpath), md5_checksum_hex(fpath)])
    return items

def get_game_info(gindex):
    rsp = rq.urlopen("https://www.66rpg.com/f/%s/ref/d3d3LjY2cnBnLmNvbQ==" % gindex)
    q = dict(urlp.parse_qsl(urlp.urlparse(rsp.url).query))
    return {
        "gindex" : q["gindex"],
        "guid" : q["guid"],
        "version" : q["version"],
    }
    

def get_manifest(uuid, ver, quality='32', api="http://cgv2.66rpg.com"):
    api_pattern = api + "/api/oapi_map.php?action=create_bin&guid=%s&version=%s&quality=%s"
    req_str = api_pattern % (uuid, ver, quality)
    rsp = json.load(rq.urlopen(req_str))
    if rsp['status'] != 2:
        raise IOError("request failed with reason %s" % rsp['msg'])
    return rsp['data']

def download_game_rsc(item, path, cdnpath, overwrite=False):
    url = "%s/shareres/%s/%s" % (cdnpath, item[2][0:2], item[2])
    fpath = path / item[0] 
    os.makedirs(fpath.parent, exist_ok=True)
    if os.path.isfile(fpath) and (not overwrite):
        return
    with rq.urlopen(url) as rsp, fpath.open('wb') as out_f:
        shutil.copyfileobj(rsp, out_f)

def download_from_manifest(data, localpath=pathlib.Path('game-rsc'), cdnpath="http://dlcdn1.cgyouxi.com"):
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        ftr_file_map = {executor.submit(download_game_rsc, item, localpath, cdnpath): item[0] for item in data}
        for future in concurrent.futures.as_completed(ftr_file_map):
            name = ftr_file_map[future]
            try:
                future.result()
            except Exception as exc:
                print('failed to download %r with exception: %s' % (name, exc))

def dump_manifest(data, filename='manifest.json'):
    with open(filename,'w') as out:
        json.dump({'status':2,'data':data}, out)

def append_packed_str(pat, args, input_str):
    b = bytes(input_str, 'utf-8')
    args.append(len(b))
    args.append(b)
    return pat + "I" + str(len(b)) + "s"

def dump_map_bin(data, filename="map.bin"):
    item_count = len(data)
    args = [item_count]
    # little endian
    pat = "<I" 
    for item in data:
        name = item[0]
        pat = append_packed_str(pat, args, name)
        itemsize = int(item[1])
        args.append(itemsize)
        pat += "I"
        md5str = item[2]
        pat = append_packed_str(pat, args, md5str)
    b = struct.pack(pat, *args)
    # return b
    with open(filename,'wb') as out:
        out.write(b)

def generate_mitm_manifest(data, uuid, filename='game-manifest.json'):
    out = {
        "mapfile" : "map.bin",
        "guid" : uuid,
    }
    hijacked = {}
    for item in data:
        hijacked[item[2]] = item[0]
    out["hijackeddata"] = hijacked
    with open(filename,'w') as f:
        json.dump(out, f)
    
def main():
    parser = argparse.ArgumentParser(description='A simple utility to scrape 66rpg games')
    subparsers = parser.add_subparsers()

    info_parser = subparsers.add_parser('info', description='''Retrieve game uuid and latest version with numerical game id''')
    info_parser.add_argument('game_id', nargs='?', type=int, default=2992, help='numerical game id as shown in 66rpg website, doesn\'t work with removed games. default to 2992 (潜伏之赤途)')

    manifest_parser = subparsers.add_parser('manifest', description='''Get game resource manifest from an online 66RPG game or a local project''')
    input_grp = manifest_parser.add_mutually_exclusive_group(required=True)
    uuid_grp = input_grp.add_mutually_exclusive_group()
    uuid_grp.add_argument('uuid', nargs='?', default=None, action='append', help='game UUID (guid), cannot coexist with --load-json')
    uuid_grp.add_argument('--uuid','-uuid', dest='uuid', action='append', help='game UUID (guid), cannot coexist with --load-json')
    ver_grp = manifest_parser.add_mutually_exclusive_group()
    ver_grp.add_argument('ver', nargs='?', default=None, action='append', help='game version, not required for sideloading local project')
    ver_grp.add_argument('--ver', '-ver', dest='ver', action='append', help='game version, not required for sideloading local project')
    manifest_parser.add_argument('--quality', nargs='?', dest='quality', default='32', help='game graphics quality, default to 32(HD)')
    input_grp.add_argument('--load-json', nargs=1, dest='input_json',
        type=argparse.FileType(mode='r'),
        help='path to an existing manifest json file, cannot coexist with --uuid')
    manifest_parser.add_argument('--local-path', nargs=1, dest='local_root',
        help='path to local project directory, should be used with option --uuid, ignored if --load-json is supplied')
    manifest_parser.add_argument('--dump-json', nargs='?', dest='output_json',
        type=argparse.FileType(mode='w'), default=argparse.SUPPRESS,
        help='path to dump the manifest in json format, default to stdout')
    manifest_parser.add_argument('--dump-binary-map', nargs=1, dest='output_mapbin',
        help='path to map.bin for mobile platform sideloading, used by MITM sideloader')
    manifest_parser.add_argument('--dump-mitm-manifest', nargs=1, dest='output_mitm',
        help='filename of game resource manifest json file used by MITM sideloader. Note that the path to \"map.bin\" is hardcoded. You can edit it manually.')
    manifest_parser.add_argument('--download', nargs='?', dest='download_path',
        default=argparse.SUPPRESS, help='download game resource with the given manifest, path default to \"game-rsc_uuid_ver\" in current working directory')

    args = parser.parse_args()
    if hasattr(args, 'game_id'):
        info = get_game_info(args.game_id)
        print("%s %s" % (info['guid'], info['version']))
    elif hasattr(args, 'uuid'):
        args.uuid = next((item for item in args.uuid if item is not None), None)
        args.ver = next((item for item in args.ver if item is not None), None)
        if args.input_json is not None:
            manifest = json.load(args.input_json)
        elif args.local_root is not None:
            manifest = generate_manifest(args.local_root)
        else:
            manifest = get_manifest(args.uuid, args.ver, args.quality)
        
        if hasattr(args, 'output_json'):
            if args.output_json is None:
                args.output_json = sys.stdout
            json.dump(manifest, args.output_json)
        if args.output_mapbin is not None:
            dump_map_bin(manifest, args.output_mapbin)
        if args.output_mitm is not None and args.uuid is not None:
            generate_mitm_manifest(manifest, args.uuid, args.output_mitm)
        if hasattr(args, 'download_path') and args.uuid is not None and args.ver is not None:
            if args.download_path is None:
                args.download_path = 'game-rsc_%s_%s' % (args.uuid, args.ver)
            download_from_manifest(manifest, pathlib.Path(args.download_path))
    else:
        parser.print_help(sys.stderr)
        sys.exit(0)

if __name__ == "__main__":
    main()

# qf_info = get_game_info('2992')
# qfzct_data = get_manifest(qf_info.guid, qf_info.version)
# download_from_manifest(qfzct_data)
# dump_manifest(qfzct_data)
# 
# mygame = generate_manifest("C:\\Users\\test\\Documents\\AvgMakerOrange\\我的作品1")
# dump_manifest(qfzct_data) # for electron version/web version
# dump_map_bin(qfzct_data)  # for sideloading on mobile platforms