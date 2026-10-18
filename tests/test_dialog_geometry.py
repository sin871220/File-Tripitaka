import ctypes
import unittest
from unittest.mock import Mock, patch

from dialog_geometry import (_MonitorInfo, _center_position, _windows_workarea,
                             _workarea, center_dialog)


class DialogGeometryChecks(unittest.TestCase):
    def make_parent(self):
        parent = Mock()
        parent.winfo_x.return_value = 200
        parent.winfo_y.return_value = 100
        parent.winfo_rootx.return_value = 200
        parent.winfo_rooty.return_value = 128
        parent.winfo_width.return_value = 1000
        parent.winfo_height.return_value = 800
        parent.winfo_vrootx.return_value = 0
        parent.winfo_vrooty.return_value = 0
        parent.winfo_vrootwidth.return_value = 1920
        parent.winfo_vrootheight.return_value = 1080
        parent.winfo_id.return_value = 1234
        return parent

    def test_center_and_clamp_to_each_edge(self):
        area = (0, 40, 1920, 1040)
        cases = [((200, 100, 1000, 800), (500, 350)),
                 ((-500, -300, 500, 300), (0, 40)),
                 ((1800, 1000, 500, 300), (1520, 740))]
        for parent_rect, expected in cases:
            with self.subTest(parent_rect=parent_rect):
                self.assertEqual(_center_position(400, 300, parent_rect, area), expected)

    def test_negative_monitor_coordinates_are_retained(self):
        self.assertEqual(_center_position(500, 400, (-1800, -900, 1200, 800),
                                          (-1920, -1080, 0, 0)), (-1450, -700))

    def test_oversized_dialog_is_anchored_without_resizing(self):
        self.assertEqual(_center_position(2200, 1400, (500, 300, 900, 600),
                                          (0, 40, 1920, 1040)), (0, 40))

    def test_final_size_is_used_instead_of_unmapped_actual_size(self):
        parent = self.make_parent()
        dialog = Mock()
        dialog.winfo_width.return_value = 1
        dialog.winfo_height.return_value = 1
        with patch('dialog_geometry.sys.platform', 'darwin'):
            self.assertEqual(center_dialog(dialog, parent, 600, 500), (400, 250))
        dialog.geometry.assert_called_once_with('600x500+400+250')
        dialog.winfo_width.assert_not_called()
        dialog.winfo_height.assert_not_called()

    def test_natural_size_sets_only_position_and_updates_before_measurement(self):
        parent = self.make_parent()
        dialog = Mock()
        dialog.winfo_reqwidth.return_value = 400
        dialog.winfo_reqheight.return_value = 300
        with patch('dialog_geometry.sys.platform', 'darwin'):
            self.assertEqual(center_dialog(dialog, parent), (500, 350))
        dialog.geometry.assert_called_once_with('+500+350')
        self.assertEqual(dialog.mock_calls[0][0], 'update_idletasks')
        dialog.bind.assert_not_called()

    def test_negative_geometry_uses_absolute_not_right_relative_syntax(self):
        parent = self.make_parent()
        parent.winfo_x.return_value = -1800
        parent.winfo_y.return_value = -900
        parent.winfo_width.return_value = 1200
        dialog = Mock()
        with patch('dialog_geometry.sys.platform', 'win32'), \
                patch('dialog_geometry._windows_workarea', return_value=(-1920, -1080, 0, 0)):
            center_dialog(dialog, parent, 500, 400)
        dialog.geometry.assert_called_once_with('500x400+-1450+-700')

    def test_titlebar_offset_is_not_added_to_the_parent_center(self):
        parent = self.make_parent()
        parent.winfo_x.return_value = 120
        parent.winfo_y.return_value = 100
        parent.winfo_rootx.return_value = 120
        parent.winfo_rooty.return_value = 128
        parent.winfo_width.return_value = 1120
        parent.winfo_height.return_value = 760
        dialog = Mock()
        with patch('dialog_geometry.sys.platform', 'darwin'):
            center_dialog(dialog, parent, 600, 590)
        dialog.geometry.assert_called_once_with('600x590+380+185')
        parent.winfo_rootx.assert_not_called()
        parent.winfo_rooty.assert_not_called()

    def test_windows_monitor_workarea_excludes_reserved_space(self):
        parent = self.make_parent()
        user = Mock()
        user.MonitorFromWindow.return_value = 5678

        def monitor_info(monitor, pointer):
            self.assertEqual(monitor, 5678)
            info = ctypes.cast(pointer, ctypes.POINTER(_MonitorInfo)).contents
            self.assertEqual(info.cbSize, ctypes.sizeof(_MonitorInfo))
            info.rcWork.left, info.rcWork.top = -1920, 30
            info.rcWork.right, info.rcWork.bottom = 0, 1040
            return 1

        user.GetMonitorInfoW.side_effect = monitor_info
        with patch('dialog_geometry.ctypes.WinDLL', create=True, return_value=user):
            self.assertEqual(_windows_workarea(parent), (-1920, 30, 0, 1040))
        user.MonitorFromWindow.assert_called_once_with(1234, 2)

    def test_failed_windows_query_falls_back_to_tk_virtual_root(self):
        parent = self.make_parent()
        parent.winfo_vrootx.return_value = -1920
        parent.winfo_vrooty.return_value = -1080
        parent.winfo_vrootwidth.return_value = 3840
        parent.winfo_vrootheight.return_value = 2160
        with patch('dialog_geometry.sys.platform', 'win32'), \
                patch('dialog_geometry._windows_workarea', return_value=None):
            self.assertEqual(_workarea(parent), (-1920, -1080, 1920, 1080))


if __name__ == '__main__':
    unittest.main()
