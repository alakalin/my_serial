import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


import serial
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QTextCharFormat, QTextCursor, QTextDocument

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial.tools import list_ports


BAUD_RATES = ["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
DATA_BITS = {
    "5": serial.FIVEBITS,
    "6": serial.SIXBITS,
    "7": serial.SEVENBITS,
    "8": serial.EIGHTBITS,
}
STOP_BITS = {
    "1": serial.STOPBITS_ONE,
    "1.5": serial.STOPBITS_ONE_POINT_FIVE,
    "2": serial.STOPBITS_TWO,
}
PARITY = {
    "None": serial.PARITY_NONE,
    "Odd": serial.PARITY_ODD,
    "Even": serial.PARITY_EVEN,
}


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


@dataclass
class SerialConfig:

    port: str
    baud_rate: int
    data_bits: int
    stop_bits_key: str
    parity: str


class SerialReadThread(QThread):
    data_received = Signal(bytes)
    error_occurred = Signal(str)

    def __init__(self, serial_port: serial.Serial):
        super().__init__()
        self.serial_port = serial_port
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            try:
                waiting = self.serial_port.in_waiting
                if waiting > 0:
                    data = self.serial_port.read(waiting)
                    if data:
                        self.data_received.emit(data)
                else:
                    self.msleep(20)
            except Exception as e:
                self.error_occurred.emit(str(e))
                break


class SerialTab(QWidget):
    status_changed = Signal(str)

    def __init__(self, tab_name: str):
        super().__init__()
        self.tab_name = tab_name
        self.serial_port: Optional[serial.Serial] = None
        self.reader_thread: Optional[SerialReadThread] = None
        self.rx_count = 0
        self.tx_count = 0
        self._build_ui()
        self.refresh_ports()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        top_layout = QGridLayout()

        self.port_combo = QComboBox()

        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(BAUD_RATES)
        self.baud_combo.setCurrentText("115200")

        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(DATA_BITS.keys())
        self.data_bits_combo.setCurrentText("8")

        self.stop_bits_combo = QComboBox()
        self.stop_bits_combo.addItems(STOP_BITS.keys())
        self.stop_bits_combo.setCurrentText("1")

        self.parity_combo = QComboBox()
        self.parity_combo.addItems(PARITY.keys())
        self.parity_combo.setCurrentText("None")

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["gbk", "gb18030", "utf-8"])
        self.encoding_combo.setCurrentText("gbk")

        self.refresh_button = QPushButton("刷新串口")
        self.open_button = QPushButton("打开串口")

        top_layout.addWidget(QLabel("串口"), 0, 0)
        top_layout.addWidget(self.port_combo, 0, 1)
        top_layout.addWidget(self.refresh_button, 0, 2)
        top_layout.addWidget(QLabel("波特率"), 0, 3)
        top_layout.addWidget(self.baud_combo, 0, 4)

        top_layout.addWidget(QLabel("数据位"), 1, 0)
        top_layout.addWidget(self.data_bits_combo, 1, 1)
        top_layout.addWidget(QLabel("停止位"), 1, 2)
        top_layout.addWidget(self.stop_bits_combo, 1, 3)
        top_layout.addWidget(QLabel("校验位"), 1, 4)
        top_layout.addWidget(self.parity_combo, 1, 5)

        top_layout.addWidget(QLabel("编码"), 0, 5)
        top_layout.addWidget(self.encoding_combo, 0, 6)
        top_layout.addWidget(self.open_button, 1, 6)

        self.receive_area = QPlainTextEdit()
        self.receive_area.setReadOnly(True)
        self.receive_area.setPlaceholderText("接收数据显示区域")

        search_top_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索关键字")
        self.search_prev_button = QPushButton("上一个")
        self.search_next_button = QPushButton("下一个")

        search_top_layout.addWidget(QLabel("搜索"))
        search_top_layout.addWidget(self.search_input, 1)
        search_top_layout.addWidget(self.search_prev_button)
        search_top_layout.addWidget(self.search_next_button)

        search_bottom_layout = QHBoxLayout()
        self.highlight_button = QPushButton("高亮全部")
        self.clear_highlight_button = QPushButton("清除高亮")
        search_bottom_layout.addWidget(self.highlight_button)
        search_bottom_layout.addWidget(self.clear_highlight_button)
        search_bottom_layout.addStretch(1)

        send_input_layout = QHBoxLayout()
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("输入要发送的数据")
        self.send_button = QPushButton("发送")
        send_input_layout.addWidget(self.send_input, 1)
        send_input_layout.addWidget(self.send_button)

        control_top_layout = QHBoxLayout()
        self.hex_mode_checkbox = QCheckBox("HEX收发")
        self.add_newline_checkbox = QCheckBox("发送附加\\r\\n")
        self.timestamp_checkbox = QCheckBox("显示时间戳")
        self.timestamp_checkbox.setChecked(True)
        self.auto_scroll_checkbox = QCheckBox("自动滚动(接收)")
        self.auto_scroll_checkbox.setChecked(True)

        control_top_layout.addWidget(self.hex_mode_checkbox)
        control_top_layout.addWidget(self.add_newline_checkbox)
        control_top_layout.addWidget(self.timestamp_checkbox)
        control_top_layout.addWidget(self.auto_scroll_checkbox)
        control_top_layout.addStretch(1)

        control_bottom_layout = QHBoxLayout()
        self.loop_send_checkbox = QCheckBox("定时发送")
        self.loop_interval_spin = QSpinBox()
        self.loop_interval_spin.setRange(10, 60000)
        self.loop_interval_spin.setValue(1000)
        self.loop_interval_spin.setSuffix(" ms")
        self.clear_button = QPushButton("清空接收区")

        control_bottom_layout.addWidget(self.loop_send_checkbox)
        control_bottom_layout.addWidget(self.loop_interval_spin)
        control_bottom_layout.addWidget(self.clear_button)
        control_bottom_layout.addStretch(1)

        self.stats_label = QLabel("RX: 0 bytes | TX: 0 bytes | 未连接")

        root_layout.addLayout(top_layout)
        root_layout.addWidget(self.receive_area, 1)
        root_layout.addLayout(search_top_layout)
        root_layout.addLayout(search_bottom_layout)
        root_layout.addLayout(send_input_layout)
        root_layout.addLayout(control_top_layout)
        root_layout.addLayout(control_bottom_layout)
        root_layout.addWidget(self.stats_label)




        self.loop_timer = QTimer(self)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.open_button.clicked.connect(self.toggle_connection)
        self.send_button.clicked.connect(self.send_data)
        self.clear_button.clicked.connect(self.clear_receive_area)
        self.loop_send_checkbox.stateChanged.connect(self._on_loop_send_changed)
        self.loop_timer.timeout.connect(self.send_data)

        self.search_prev_button.clicked.connect(lambda: self.find_text(forward=False))
        self.search_next_button.clicked.connect(lambda: self.find_text(forward=True))
        self.search_input.returnPressed.connect(lambda: self.find_text(forward=True))
        self.highlight_button.clicked.connect(self.highlight_all_matches)
        self.clear_highlight_button.clicked.connect(self.clear_highlight)


    def _on_loop_send_changed(self, state: int) -> None:
        if state == Qt.Checked:
            self.loop_timer.start(self.loop_interval_spin.value())
        else:
            self.loop_timer.stop()

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(ports)
        if current and current in ports:
            self.port_combo.setCurrentText(current)

    def get_config(self) -> SerialConfig:
        return SerialConfig(
            port=self.port_combo.currentText().strip(),
            baud_rate=int(self.baud_combo.currentText().strip()),
            data_bits=DATA_BITS[self.data_bits_combo.currentText()],
            stop_bits_key=self.stop_bits_combo.currentText(),
            parity=PARITY[self.parity_combo.currentText()],
        )

    def toggle_connection(self) -> None:
        if self.serial_port and self.serial_port.is_open:
            self.close_port()
            return

        try:
            cfg = self.get_config()
            if not cfg.port:
                QMessageBox.warning(self, "提示", "请先选择可用串口")
                return

            self.serial_port = serial.Serial(
                port=cfg.port,
                baudrate=cfg.baud_rate,
                bytesize=cfg.data_bits,
                stopbits=STOP_BITS[cfg.stop_bits_key],
                parity=cfg.parity,
                timeout=0.1,
            )

            self.reader_thread = SerialReadThread(self.serial_port)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error)
            self.reader_thread.start()

            self.open_button.setText("关闭串口")
            self.update_stats("已连接")
            self.status_changed.emit(f"{self.tab_name} 已连接 {cfg.port}")
        except ValueError:
            QMessageBox.critical(self, "参数错误", "波特率必须是数字")
        except Exception as e:
            QMessageBox.critical(self, "打开串口失败", str(e))

    def close_port(self) -> None:
        if self.reader_thread:
            self.reader_thread.stop()
            self.reader_thread.wait(500)
            self.reader_thread = None

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

        self.serial_port = None
        self.open_button.setText("打开串口")
        self.update_stats("未连接")
        self.status_changed.emit(f"{self.tab_name} 已断开")

    def on_error(self, error: str) -> None:
        self.append_log(f"[错误] {error}")
        self.close_port()

    def append_log(self, text: str) -> None:
        self.receive_area.appendPlainText(text)
        if self.auto_scroll_checkbox.isChecked():
            scrollbar = self.receive_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())


    def _decode_bytes(self, data: bytes) -> str:
        encoding = self.encoding_combo.currentText().strip() or "gbk"
        try:
            return data.decode(encoding, errors="replace")
        except LookupError:
            return data.decode("gbk", errors="replace")

    @staticmethod
    def _bytes_to_hex(data: bytes) -> str:
        return " ".join(f"{b:02X}" for b in data)

    def _format_rx_text(self, data: bytes) -> str:
        if self.hex_mode_checkbox.isChecked():
            return self._bytes_to_hex(data)
        return self._decode_bytes(data)

    def on_data_received(self, data: bytes) -> None:
        self.rx_count += len(data)
        body = self._format_rx_text(data)

        if self.timestamp_checkbox.isChecked():
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.append_log(f"[{ts}] RX: {body}")
        else:
            self.append_log(body)

        self.update_stats("已连接")

    def _parse_send_payload(self, text: str) -> bytes:
        if self.hex_mode_checkbox.isChecked():
            normalized = re.sub(r"\s+", " ", text.strip())
            if not normalized:
                return b""
            try:
                payload = bytes.fromhex(normalized)
            except ValueError as e:
                raise ValueError("HEX格式错误，请输入如: 01 A0 FF") from e
            if self.add_newline_checkbox.isChecked():
                payload += b"\r\n"
            return payload

        if self.add_newline_checkbox.isChecked():
            text += "\r\n"

        encoding = self.encoding_combo.currentText().strip() or "gbk"
        try:
            return text.encode(encoding, errors="replace")
        except LookupError:
            return text.encode("gbk", errors="replace")

    def send_data(self) -> None:
        text = self.send_input.text()
        if not text:
            return

        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "提示", "请先打开串口")
            return

        try:
            payload = self._parse_send_payload(text)
            if not payload:
                return

            sent = self.serial_port.write(payload)
            self.tx_count += sent

            if self.timestamp_checkbox.isChecked():
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                tx_body = self._bytes_to_hex(payload) if self.hex_mode_checkbox.isChecked() else text
                self.append_log(f"[{ts}] TX: {tx_body}")

            self.update_stats("已连接")
        except ValueError as e:
            QMessageBox.warning(self, "发送参数错误", str(e))
        except Exception as e:
            QMessageBox.critical(self, "发送失败", str(e))

    def find_text(self, forward: bool = True) -> None:
        keyword = self.search_input.text()
        if not keyword:
            return

        flags = QTextDocument.FindFlag()
        if not forward:
            flags |= QTextDocument.FindBackward

        found = self.receive_area.find(keyword, flags)
        if found:
            return

        cursor = self.receive_area.textCursor()
        cursor.movePosition(QTextCursor.Start if forward else QTextCursor.End)
        self.receive_area.setTextCursor(cursor)
        self.receive_area.find(keyword, flags)

    def highlight_all_matches(self) -> None:
        keyword = self.search_input.text()
        if not keyword:
            return

        doc = self.receive_area.document()
        selections = []
        search_cursor = QTextCursor(doc)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FFE58F"))

        while True:
            search_cursor = doc.find(keyword, search_cursor)
            if search_cursor.isNull():
                break

            selection = QTextEdit.ExtraSelection()
            selection.cursor = search_cursor
            selection.format = fmt
            selections.append(selection)

        self.receive_area.setExtraSelections(selections)


    def clear_highlight(self) -> None:
        self.receive_area.setExtraSelections([])

    def clear_receive_area(self) -> None:
        self.receive_area.clear()
        self.clear_highlight()

    def update_stats(self, status_text: str) -> None:
        self.stats_label.setText(f"RX: {self.rx_count} bytes | TX: {self.tx_count} bytes | {status_text}")

    def shutdown(self) -> None:
        self.loop_timer.stop()
        self.close_port()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("简约串口助手")
        self.resize(1280, 760)
        self.tab_count = 0

        central = QWidget()
        layout = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        self.add_left_button = QPushButton("新增左侧标签")
        self.add_right_button = QPushButton("新增右侧标签")
        self.remove_left_button = QPushButton("关闭左侧当前")
        self.remove_right_button = QPushButton("关闭右侧当前")
        self.global_refresh_button = QPushButton("刷新全部串口")

        top_bar.addWidget(self.add_left_button)
        top_bar.addWidget(self.add_right_button)
        top_bar.addWidget(self.remove_left_button)
        top_bar.addWidget(self.remove_right_button)
        top_bar.addWidget(self.global_refresh_button)
        top_bar.addStretch(1)

        self.left_tabs = QTabWidget()
        self.right_tabs = QTabWidget()
        self.left_tabs.setTabsClosable(False)
        self.right_tabs.setTabsClosable(False)

        self.content_widget = QWidget()
        self.content_layout = QHBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        self.content_layout.addWidget(self.left_tabs, 1)
        self.content_layout.addWidget(self.right_tabs, 1)

        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setMaximumHeight(24)

        layout.addLayout(top_bar)
        layout.addWidget(self.content_widget, 1)
        layout.addWidget(self.status_label, 0)
        self.setCentralWidget(central)

        self.add_left_button.clicked.connect(lambda: self.add_serial_tab("left"))
        self.add_right_button.clicked.connect(lambda: self.add_serial_tab("right"))
        self.remove_left_button.clicked.connect(lambda: self.remove_current_tab("left"))
        self.remove_right_button.clicked.connect(lambda: self.remove_current_tab("right"))
        self.global_refresh_button.clicked.connect(self.refresh_all_ports)

        self.add_serial_tab("left")

    def _next_tab_name(self) -> str:
        self.tab_count += 1
        return f"串口{self.tab_count}"

    def _total_tabs(self) -> int:
        return self.left_tabs.count() + self.right_tabs.count()

    def _pop_tab(self, source_tabs: QTabWidget, index: int):
        widget = source_tabs.widget(index)
        title = source_tabs.tabText(index)
        source_tabs.removeTab(index)
        return widget, title

    def _sync_split_view(self) -> None:
        total = self._total_tabs()

        if total <= 1:
            if self.left_tabs.count() == 0 and self.right_tabs.count() == 1:
                widget, title = self._pop_tab(self.right_tabs, 0)
                self.left_tabs.addTab(widget, title)
                self.left_tabs.setCurrentWidget(widget)

            self.right_tabs.hide()
        else:
            if self.left_tabs.count() == 0 and self.right_tabs.count() > 0:
                widget, title = self._pop_tab(self.right_tabs, 0)
                self.left_tabs.addTab(widget, title)
            elif self.right_tabs.count() == 0 and self.left_tabs.count() > 1:
                widget, title = self._pop_tab(self.left_tabs, self.left_tabs.count() - 1)
                self.right_tabs.addTab(widget, title)

            self.right_tabs.show()

        self.remove_left_button.setEnabled(self.left_tabs.count() > 0)
        self.remove_right_button.setEnabled(self.right_tabs.count() > 0)

    def add_serial_tab(self, side: str) -> None:
        name = self._next_tab_name()
        tab = SerialTab(name)
        tab.status_changed.connect(self.status_label.setText)

        if self._total_tabs() == 1:
            target_tabs = self.right_tabs if self.left_tabs.count() == 1 else self.left_tabs
        else:
            target_tabs = self.left_tabs if side == "left" else self.right_tabs

        target_tabs.addTab(tab, name)
        target_tabs.setCurrentWidget(tab)
        self._sync_split_view()

    def remove_current_tab(self, side: str) -> None:
        target_tabs = self.left_tabs if side == "left" else self.right_tabs
        current_idx = target_tabs.currentIndex()
        if current_idx < 0:
            return

        widget = target_tabs.widget(current_idx)
        if isinstance(widget, SerialTab):
            widget.shutdown()
        target_tabs.removeTab(current_idx)
        widget.deleteLater()
        self._sync_split_view()

    def _iter_all_serial_tabs(self):
        for tabs in (self.left_tabs, self.right_tabs):
            for i in range(tabs.count()):
                widget = tabs.widget(i)
                if isinstance(widget, SerialTab):
                    yield widget

    def refresh_all_ports(self) -> None:
        for tab in self._iter_all_serial_tabs():
            tab.refresh_ports()
        self.status_label.setText("已刷新全部串口列表")

    def closeEvent(self, event) -> None:
        for tab in self._iter_all_serial_tabs():
            tab.shutdown()
        super().closeEvent(event)




def main() -> None:
    app = QApplication(sys.argv)
    icon_path = resource_path(os.path.join("assets", "app.ico"))
    icon = QIcon(icon_path)
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
