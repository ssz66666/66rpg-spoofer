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
import datetime as dt
import re
import warnings

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
                if (dir == "data") and bool(re.match('story', f, re.I)):
                    continue
                # ignore apple double files
                if f.startswith("._"):
                    continue
                if bool(re.match('.ds_store', f, re.I)):
                    continue
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

def read_int32(fd):
    buf = fd.read(4)
    return struct.unpack("<I", buf)[0]

def read_packed_str(fd):
    slen = read_int32(fd)
    buf = fd.read(slen)
    if len(buf) != slen:
        raise ValueError("ill-formed packed string")
    return buf.decode() # utf-8 encoded string

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

def make_android_metadata(meta):
    # make game.in

    # TODO: generate metadata upon needs
    pass

def make_android_res(data, localdir, outdir):
    # make game.oge and corresponding map.oge

    # pattern for map.oge
    # signature and version
    args = [b"ORGRES\x05\x00\x00\x00"]
    pat = "<10s"

    # number of files
    args.append(len(data))
    pat += "I"

    offset = 0x6
    for game_file in data:
        # file name
        pat = append_packed_str(pat, args, game_file[0])
        # md5 hash
        pat = append_packed_str(pat, args, game_file[2])
        # size
        item_size = game_file[1]
        args.append(item_size)
        pat += "I"
        # offset
        args.append(offset)
        pat += "I"
        offset += item_size
    map_b = struct.pack(pat, *args)

    with open(pathlib.Path(outdir, "map.oge"),'wb') as out:
        out.write(map_b)

    with open(pathlib.Path(outdir, "game.oge"),'wb') as wfd:
        # write signature
        wfd.write(b"ORGMUL")
        wfd.flush()
        for item in data:
            with open(pathlib.Path(localdir, item[0]),'rb') as fd:
                shutil.copyfileobj(fd, wfd)

def unpack_android_res(indir, outdir, check_md5=True):
    # unpack resource from game.oge + map.oge
    itemlst = []
    with open(pathlib.Path(indir, "map.oge"), "rb") as mapfd:
        buf = mapfd.read(6)
        if buf != b"ORGRES":
            raise ValueError("bad map.oge signature")
        vernum = read_int32(mapfd)
        if vernum != 5:
            raise ValueError(f"unrecognised version number: {vernum}")
        nitems = read_int32(mapfd)
        while True:
            buf = mapfd.read(4)
            if not buf:
                break
            slen = struct.unpack("<I", buf)[0]
            buf = mapfd.read(slen)
            if len(buf) != slen:
                raise ValueError("ill-formed packed string")
            fname = buf.decode()
            md5_checksum = read_packed_str(mapfd)
            fsize = read_int32(mapfd)
            foffset = read_int32(mapfd)
            itemlst.append([fname, md5_checksum, fsize, foffset])
        if nitems != len(itemlst):
            warnings.warn("number of resource items mismatch, possibly corrupted files")

    # copied from https://github.com/python/cpython/blob/5faff977adbe089e1f91a5916ccb2160a22dd292/Lib/shutil.py#L52
    COPY_BUFSIZE = 1024 * 1024 if os.name == 'nt' else 64 * 1024

    with open(pathlib.Path(indir, "game.oge"), "rb") as datafd:
        for item in itemlst:
            if check_md5:
                hash_md5 = hashlib.md5()
            
            fpath = pathlib.Path(outdir, item[0])
            os.makedirs(fpath.parent, exist_ok=True)
            with open(fpath, "wb") as wfd:
                fmd5 = item[1]
                flen = item[2]
                foffset = item[3]
                datafd.seek(foffset, 0)
                nblks, rem = divmod(flen, COPY_BUFSIZE)
                for _ in range(nblks):
                    buf = datafd.read(COPY_BUFSIZE)
                    if len(buf) < COPY_BUFSIZE:
                        raise IOError("unexpected EOF")
                    if check_md5:
                        hash_md5.update(buf)
                    wfd.write(buf)
                if rem > 0:
                    buf = datafd.read(rem)
                    if len(buf) < rem:
                        raise IOError("unexpected EOF")
                    if check_md5:
                        hash_md5.update(buf)
                    wfd.write(buf)
                if check_md5:
                    if hash_md5.hexdigest() != fmd5:
                        warnings.warn(f"file {item[0]} MD5 checksum mismatch")

def pack_android(data, meta, localdir, outdir):
    pass

def pack_sideloader(data, uuid, localdir, outdir):
    dump_map_bin(data, filename=pathlib.Path(outdir, "map.bin"))
    generate_mitm_manifest(data, uuid, filename=pathlib.Path(outdir, "game-manifest.json"))
    # copy over resource files
    for item in data:
        src_path = pathlib.Path(localdir, item[0])
        dest_path = pathlib.Path(outdir, item[0])
        os.makedirs(dest_path.parent, exist_ok=True)
        shutil.copyfile(src_path, dest_path)

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
    input_grp.add_argument('--load-json', dest='input_json',
        type=argparse.FileType(mode='r'),
        help='path to an existing manifest json file, cannot coexist with --uuid')
    manifest_parser.add_argument('--local-path', dest='local_root',
        help='path to local project directory, should be used with option --uuid, ignored if --load-json is supplied')
    manifest_parser.add_argument('--dump-json', nargs='?', dest='output_json',
        type=argparse.FileType(mode='w'), default=argparse.SUPPRESS,
        help='path to dump the manifest in json format, default to stdout')
    manifest_parser.add_argument('--dump-api-response', dest='output_api_response',
        help='path to manifest.json for web/electron edition')
    manifest_parser.add_argument('--dump-binary-map', dest='output_mapbin',
        help='path to map.bin for mobile platform sideloading, used by MITM sideloader')
    manifest_parser.add_argument('--dump-mitm-manifest', dest='output_mitm',
        help='filename of game resource manifest json file used by MITM sideloader. Note that the path to \"map.bin\" is hardcoded. You can edit it manually.')
    manifest_parser.add_argument('--download', nargs='?', dest='download_path',
        default=argparse.SUPPRESS, help='download game resource with the given manifest, path default to \"game-rsc_uuid_ver\" in current working directory')
    manifest_parser.add_argument('--pack-android-resource', dest='output_android',
        help='path to output the packed android game resource, must be used with --local-path')
    manifest_parser.add_argument('--pack-sideloader', dest='output_sideloader',
        help='path to output the packed game resource and manifest for use with MITM sideloader, must be used with --local-path. A valid uuid is required')
    manifest_parser.add_argument('--unpack-android-resource', dest='output_unpacked',
        help='path to output the unpacked android game resource, must be used with --local-path pointing to the directory containing both map.oge and game.oge')

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
        if args.output_api_response is not None:
            dump_manifest(manifest, args.output_api_response)
        if args.output_mapbin is not None:
            dump_map_bin(manifest, args.output_mapbin)
        if args.output_mitm is not None and args.uuid is not None:
            generate_mitm_manifest(manifest, args.uuid, args.output_mitm)
        if hasattr(args, 'download_path'):
            if args.download_path is None and args.uuid is not None and args.ver is not None:
                args.download_path = 'game-rsc_%s_%s' % (args.uuid, args.ver)
            download_from_manifest(manifest, pathlib.Path(args.download_path))
        if args.output_android is not None and args.local_root is not None:
            os.makedirs(args.output_android, exist_ok=True)
            make_android_res(manifest, args.local_root, args.output_android)
        if args.output_sideloader is not None and args.local_root is not None:
            pack_sideloader(manifest, args.uuid, args.local_root, args.output_sideloader)
        if args.output_unpacked is not None and args.local_root is not None:
            unpack_android_res(args.local_root, args.output_unpacked)
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