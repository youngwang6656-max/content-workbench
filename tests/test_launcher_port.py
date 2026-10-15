import socket
import pytest


def test_launcher_refuses_occupied_port_before_opening_database(tmp_path):
    from waypoint.launcher import launch
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        listener.listen(1)
        port=listener.getsockname()[1]
        with pytest.raises(RuntimeError,match='端口.*占用'):
            launch(tmp_path,port=port,open_browser=False)
    assert not (tmp_path/'waypoint.sqlite').exists()
