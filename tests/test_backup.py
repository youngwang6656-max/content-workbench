from test_repository import make
import pytest,zipfile

def test_backup_restore_and_corruption(tmp_path):
    from waypoint.backup import Backup
    r,p,t=make(tmp_path);r.save_revision(t,'english','Original.',expected_epoch=0)
    (r.db.root/'attachments'/'test.txt').write_text('attachment')
    b=Backup(r);path=b.create_backup(tmp_path/'archives')
    r.update_task(t,{'raw_input':'Changed'})
    b.restore_backup(path)
    assert r.task(t)['raw_input']=='我的想法'
    assert r.revision(r.task(t)['active']['english'])['body']=='Original.'
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../../escape','bad')
    with pytest.raises(ValueError):b.restore_backup(bad)
    assert r.task(t)['raw_input']=='我的想法'
    assert list((tmp_path/'rollback').glob('*.zip'))
