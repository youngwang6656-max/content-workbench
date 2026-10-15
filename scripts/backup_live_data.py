"""Create a verified, private pre-update backup of the local business data."""

import hashlib
import json
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from waypoint.launcher import data_directory


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='before_update')
    parser.add_argument('--output',type=Path,help='备份输出目录；默认当前源码目录的同级 backups')
    args = parser.parse_args()
    if not args.label.replace('_', '').isalnum() or len(args.label) > 40:
        raise SystemExit('备份标签只能包含字母、数字和下划线')
    workspace = Path(__file__).resolve().parents[2]
    root = (args.output or workspace / 'backups').resolve()
    root.mkdir(parents=True,exist_ok=True)
    source = data_directory()
    if not source.is_dir():
        raise SystemExit('未找到本机业务目录')
    target = (root / (args.label + '_' + datetime.now().strftime('%Y%m%d_%H%M%S'))).resolve()
    if root not in target.parents or target.exists():
        raise SystemExit('备份目标路径不安全')
    target.mkdir()
    src_db = source / 'waypoint.sqlite'
    dst_db = target / 'waypoint.sqlite'
    with sqlite3.connect(f'file:{src_db.as_posix()}?mode=ro', uri=True) as src:
        with sqlite3.connect(dst_db) as dst:
            src.backup(dst)
    with sqlite3.connect(dst_db) as db:
        result = db.execute('PRAGMA integrity_check').fetchone()[0]
        if result != 'ok':
            raise RuntimeError('数据库备份完整性检查失败：' + result)
    files = []
    attachments = source / 'attachments'
    if attachments.is_dir():
        for original in attachments.rglob('*'):
            if not original.is_file():
                continue
            relative = original.relative_to(source)
            copied = target / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, copied)
            if digest(original) != digest(copied):
                raise RuntimeError('附件备份校验失败：' + str(relative))
            files.append(str(relative))
    manifest = {'database_integrity': 'ok', 'attachments': len(files), 'files': files}
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'backup': str(target), 'database_integrity': 'ok', 'attachments': len(files)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
