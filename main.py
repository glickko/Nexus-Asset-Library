# Nexus Protocol: Media Asset Nexus v2.9
# A synergistic Python application for managing and processing media assets.
# Evolved with a persistent volume slider and robust UI icons.

import sys
import os
import subprocess
import pathlib
import json
import re

from PySide6.QtCore import (
    Qt, QUrl, QDir, QMimeData, QSize, QStandardPaths, Slot, QThread, Signal,
    QSortFilterProxyModel, QPoint, QModelIndex, QRect, QTime, QTimer
)
from PySide6.QtGui import (
    QGuiApplication, QDrag, QPixmap, QPainter, QIcon, QFont, QRegion, QColor,
    QPen, QStandardItemModel, QStandardItem, QBrush, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QFrame, QTreeView, QPushButton,
    QLabel, QFileDialog, QListWidget, QListWidgetItem, QInputDialog,
    QStyle, QMessageBox, QLineEdit, QCheckBox, QSlider
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

# --- Worker Thread for Thumbnail Generation ---
class ThumbnailGenerator(QThread):
    thumbnailReady = Signal(object, QIcon) # Pass back the item and the icon

    def __init__(self, item, media_path, thumb_path, ffmpeg_path, parent=None):
        super().__init__(parent)
        self.item = item
        self.media_path = media_path
        self.thumb_path = thumb_path
        self.ffmpeg_path = ffmpeg_path

    def run(self):
        try:
            if not os.path.exists(self.thumb_path):
                # Use a safer seek time for short clips and prevent hanging
                command = [
                    self.ffmpeg_path, '-nostdin', '-ss', '00:00:00.1', '-i', self.media_path,
                    '-vframes', '1', '-vf', 'scale=128:-1', self.thumb_path
                ]
                subprocess.run(
                    command, check=True, capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
            if os.path.exists(self.thumb_path):
                self.thumbnailReady.emit(self.item, QIcon(self.thumb_path))
        except Exception as e:
            # Silently fail for audio files or errors, the placeholder icon will remain
            print(f"Could not generate thumbnail for {self.media_path}: {e.stderr if hasattr(e, 'stderr') else e}")


# --- Custom Proxy Model for Recursive Filtering ---
class RecursiveFilterProxyModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, source_row, source_parent):
        if self.filter_accepts_row_itself(source_row, source_parent):
            return True
        source_index = self.sourceModel().index(source_row, 0, source_parent)
        if not source_index.isValid():
            return False
        for i in range(self.sourceModel().rowCount(source_index)):
            if self.filterAcceptsRow(i, source_index):
                return True
        return False

    def filter_accepts_row_itself(self, source_row, source_parent):
        return super().filterAcceptsRow(source_row, source_parent)

# --- Custom Widget for Draggable Cached Files ---
class DraggableListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setIconSize(QSize(128, 72))
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setWordWrap(True)


    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item:
            file_path = item.data(Qt.UserRole)
            if file_path:
                url = QUrl.fromLocalFile(file_path)
                mime_data = QMimeData()
                mime_data.setUrls([url])
                drag = QDrag(self)
                drag.setMimeData(mime_data)
                
                pixmap = item.icon().pixmap(self.iconSize())
                drag.setPixmap(pixmap)
                drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
                drag.exec(Qt.CopyAction)

# --- Professional Trimming Slider ---
class ProTrimSlider(QWidget):
    positionChanged = Signal(int)
    startMarkerChanged = Signal(int)
    endMarkerChanged = Signal(int)
    sliderPressed = Signal()
    sliderReleased = Signal()


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self._min_val, self._max_val = 0, 100
        self._position, self._start_marker, self._end_marker = 0, 0, 100
        self._dragging = None # Can be 'position', 'start', or 'end'
        self.handle_width = 16
        self.snap_threshold_px = 10
        
        self.pulse_alpha = 1.0
        self.pulse_direction = -1
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._animate_pulse)
        self.pulse_timer.start(50) # Controls animation speed


    def _animate_pulse(self):
        step = 0.05
        if self.pulse_alpha <= 0.5: self.pulse_direction = 1
        elif self.pulse_alpha >= 1.0: self.pulse_direction = -1
        self.pulse_alpha += step * self.pulse_direction
        self.update()

    def _value_to_pos(self, value):
        track_width = self.width() - self.handle_width
        clamped_value = max(self._min_val, min(value, self._max_val))
        if (self._max_val - self._min_val) == 0: return self.handle_width // 2
        return int((clamped_value - self._min_val) / (self._max_val - self._min_val) * track_width) + self.handle_width // 2

    def _pos_to_value(self, pos):
        track_width = self.width() - self.handle_width
        if track_width <= 0: return self._min_val
        val = self._min_val + (pos - self.handle_width // 2) / track_width * (self._max_val - self._min_val)
        return max(self._min_val, min(self._max_val, int(val)))

    def setRange(self, min_val, max_val):
        self._min_val, self._max_val = min_val, max_val
        self.update()

    def setPosition(self, value):
        if self._position != value: self._position = value; self.update()

    def setStartMarker(self, value):
        if self._start_marker != value: self._start_marker = value; self.update()

    def setEndMarker(self, value):
        if self._end_marker != value: self._end_marker = value; self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        h = self.height(); w = self.width()
        track_y = h // 2 - 4
        track_height = 8
        handle_half = self.handle_width // 2

        pos_x = self._value_to_pos(self._position)
        start_x = self._value_to_pos(self._start_marker)
        end_x = self._value_to_pos(self._end_marker)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4f4f4f"))
        painter.drawRoundedRect(handle_half, track_y, w - self.handle_width, track_height, 4, 4)

        pulse_color = QColor("#007acc")
        pulse_color.setAlphaF(self.pulse_alpha)
        painter.setBrush(pulse_color)
        painter.drawRoundedRect(start_x, track_y, end_x - start_x, track_height, 4, 4)

        self._draw_handle(painter, start_x, QColor("#2ecc71"), "[", self._dragging == 'start')
        self._draw_handle(painter, end_x, QColor("#e74c3c"), "]", self._dragging == 'end')
        
        if self._min_val <= self._position <= self._max_val:
            playhead_path = QPainterPath()
            playhead_path.moveTo(pos_x, track_y - 6)
            playhead_path.lineTo(pos_x - 5, track_y - 12)
            playhead_path.lineTo(pos_x + 5, track_y - 12)
            playhead_path.closeSubpath()
            is_snapping = abs(pos_x - start_x) < self.snap_threshold_px or abs(pos_x - end_x) < self.snap_threshold_px
            painter.setBrush(QColor("#f1c40f") if is_snapping and self._dragging == 'position' else QColor("#ecf0f1"))
            painter.setPen(QPen(QColor("#bdc3c7"), 1))

            if self._dragging == 'position':
                glow_color = QColor("#f1c40f")
                glow_color.setAlpha(100)
                painter.setPen(QPen(glow_color, 6))
                painter.drawPath(playhead_path)

            painter.drawPath(playhead_path)
            painter.setPen(QPen(QColor("#ecf0f1"), 2))
            painter.drawLine(pos_x, track_y - 6, pos_x, track_y + track_height + 6)
    
    def _draw_handle(self, painter, x, color, text, is_dragging):
        if is_dragging:
            glow_color = QColor(color)
            glow_color.setAlpha(100)
            painter.setBrush(glow_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x - self.handle_width, self.height()//2 - self.handle_width, self.handle_width*2, self.handle_width*2, 8, 8)

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(x - self.handle_width//2, self.height()//2 - self.handle_width//2, self.handle_width, self.handle_width, 4, 4)
        painter.setPen(Qt.white)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(x-self.handle_width//2, self.height()//2 - self.handle_width//2, self.handle_width, self.handle_width), Qt.AlignCenter, text)

    def mousePressEvent(self, event):
        pos_x = self._value_to_pos(self._position)
        start_x = self._value_to_pos(self._start_marker)
        end_x = self._value_to_pos(self._end_marker)
        ex = event.position().x()

        if abs(ex - start_x) < self.handle_width // 2: self._dragging = 'start'
        elif abs(ex - end_x) < self.handle_width // 2: self._dragging = 'end'
        elif abs(ex - pos_x) < self.handle_width // 2: self._dragging = 'position'
        else: self._dragging = 'position'
        
        self.sliderPressed.emit()
        self.mouseMoveEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging: return
        
        is_shift_pressed = bool(QGuiApplication.keyboardModifiers() & Qt.ShiftModifier)
        fine_tune_factor = 0.25 if is_shift_pressed else 1.0
        
        current_val = self._pos_to_value(event.position().x())
        
        if self._dragging == 'position':
            self.positionChanged.emit(current_val)
        elif self._dragging == 'start':
            prev_val = self._start_marker
            new_val = prev_val + (current_val - prev_val) * fine_tune_factor
            if new_val < self._end_marker: self.startMarkerChanged.emit(int(new_val))
        elif self._dragging == 'end':
            prev_val = self._end_marker
            new_val = prev_val + (current_val - prev_val) * fine_tune_factor
            if new_val > self._start_marker: self.endMarkerChanged.emit(int(new_val))
        self.update()

    def mouseReleaseEvent(self, event):
        if self._dragging == 'position':
            pos_x = self._value_to_pos(self._position)
            start_x = self._value_to_pos(self._start_marker)
            end_x = self._value_to_pos(self._end_marker)
            if abs(pos_x - start_x) < self.snap_threshold_px: self.positionChanged.emit(self._start_marker)
            elif abs(pos_x - end_x) < self.snap_threshold_px: self.positionChanged.emit(self._end_marker)
        
        self._dragging = None
        self.update()
        self.sliderReleased.emit()

# --- Main Application Window ---
class MainWindow(QMainWindow):
    VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv']
    AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.aac']
    SUPPORTED_MEDIA_TYPES = VIDEO_EXTENSIONS + AUDIO_EXTENSIONS

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Asset Nexus")
        self.setFixedSize(1400, 900)
        self.move(QGuiApplication.primaryScreen().availableGeometry().center() - self.rect().center())

        self.ffmpeg_path = self.check_ffmpeg()
        self.current_media_path = None
        self.cache_dir = self.setup_cache_directory()
        self.thumb_cache_dir = self.setup_cache_directory("thumbnails")
        self.config_path = os.path.join(pathlib.Path(__file__).parent, "nexus_config.json")
        
        self.config = self.load_config()
        self.library_paths = self.config.get("library_paths", [])
        self.library_view_mode = self.config.get("library_view_mode", "thumbnails")
        self.cache_view_mode = self.config.get("cache_view_mode", "thumbnails")
        self.volume = self.config.get("volume", 100)

        self.start_time_ms = 0
        self.end_time_ms = 0
        self.thumbnail_workers = []
        self.was_playing_before_drag = False

        self.setup_ui()
        self.audio_output.setVolume(self.volume / 100.0)
        self.populate_libraries()
        self.load_cache()
        self.apply_view_modes()
        
        if not self.ffmpeg_path: self.show_ffmpeg_warning()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                try:
                    data = json.load(f)
                    # Handle legacy config which was just a list of paths
                    if isinstance(data, list):
                        return {"library_paths": data, "library_view_mode": "thumbnails", "cache_view_mode": "thumbnails", "volume": 100}
                    return data if isinstance(data, dict) else {}
                except json.JSONDecodeError:
                    return {}  # Return empty dict if config is corrupt
        return {} # Return empty dict if file doesn't exist

    def save_config(self):
        config_data = {
            "library_paths": self.library_paths,
            "library_view_mode": self.library_view_mode,
            "cache_view_mode": self.cache_view_mode,
            "volume": self.volume
        }
        with open(self.config_path, 'w') as f:
            json.dump(config_data, f, indent=4)

    def setup_cache_directory(self, subfolder=""):
        cache_path = pathlib.Path(__file__).parent / "nexus_cache" / subfolder
        cache_path.mkdir(parents=True, exist_ok=True)
        return str(cache_path)

    def check_ffmpeg(self):
        try:
            cmd = ['where', 'ffmpeg'] if sys.platform == "win32" else ['which', 'ffmpeg']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return result.stdout.strip().split('\n')[0]
        except (subprocess.CalledProcessError, FileNotFoundError): return None

    def show_ffmpeg_warning(self):
        QMessageBox.warning(self, "FFmpeg Not Found", "The core processing engine, FFmpeg, was not found in your system's PATH. Trimming and thumbnail features will be disabled.")
            
    def setup_ui(self):
        self.setStyleSheet(self.get_stylesheet())
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(main_splitter, 1)

        # --- Left Pane: File System Explorer ---
        explorer_frame = QFrame()
        explorer_frame.setFrameShape(QFrame.StyledPanel)
        explorer_layout = QVBoxLayout(explorer_frame)
        
        library_top_controls = QHBoxLayout()
        btn_add_library = QPushButton("Add Library")
        btn_add_library.clicked.connect(self.add_library)
        btn_remove_library = QPushButton("Remove Library")
        btn_remove_library.clicked.connect(self.remove_library)
        library_top_controls.addWidget(btn_add_library)
        library_top_controls.addWidget(btn_remove_library)
        library_top_controls.addStretch()

        btn_lib_details = QPushButton()
        btn_lib_details.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        btn_lib_details.clicked.connect(lambda: self.set_library_view_mode("details"))
        btn_lib_thumbs = QPushButton()
        btn_lib_thumbs.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIconView))
        btn_lib_thumbs.clicked.connect(lambda: self.set_library_view_mode("thumbnails"))
        library_top_controls.addWidget(btn_lib_details)
        library_top_controls.addWidget(btn_lib_thumbs)
        explorer_layout.addLayout(library_top_controls)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search assets...")
        self.search_bar.textChanged.connect(self.on_search_text_changed)
        explorer_layout.addWidget(self.search_bar)

        self.library_model = QStandardItemModel()
        self.library_model.setHorizontalHeaderLabels(['Asset Libraries'])

        self.proxy_model = RecursiveFilterProxyModel()
        self.proxy_model.setSourceModel(self.library_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setRecursiveFilteringEnabled(True)

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.proxy_model)
        self.tree_view.doubleClicked.connect(self.on_file_selected)
        self.tree_view.setColumnWidth(0, 250)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(20)
        explorer_layout.addWidget(self.tree_view)
        
        # --- Center Pane: Media Viewer and Trimmer ---
        viewer_frame = QWidget()
        viewer_frame.setFocusPolicy(Qt.StrongFocus)
        viewer_layout = QVBoxLayout(viewer_frame)
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        self.video_widget = QVideoWidget()
        self.media_player.setVideoOutput(self.video_widget)
        self.lbl_media_name = QLabel("No Media Loaded")
        self.lbl_media_name.setAlignment(Qt.AlignCenter)
        self.lbl_media_name.setObjectName("MediaTitle")

        self.lbl_big_timestamp = QLabel("00:00.000 / 00:00.000")
        self.lbl_big_timestamp.setObjectName("BigTimestamp")
        
        playback_controls = QWidget()
        playback_layout = QHBoxLayout(playback_controls)
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_play.clicked.connect(self.play_media)
        
        self.loop_checkbox = QCheckBox("Loop")
        
        self.position_slider = ProTrimSlider()
        self.position_slider.positionChanged.connect(self.set_position)
        self.position_slider.startMarkerChanged.connect(self.set_start_time_from_slider)
        self.position_slider.endMarkerChanged.connect(self.set_end_time_from_slider)
        self.position_slider.sliderPressed.connect(self.on_slider_pressed)
        self.position_slider.sliderReleased.connect(self.on_slider_released)

        volume_icon = QLabel()
        volume_icon.setPixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(QSize(24, 24)))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.volume)
        self.volume_slider.setFixedWidth(150)
        self.volume_slider.valueChanged.connect(self.set_volume)

        playback_layout.addWidget(self.btn_play)
        playback_layout.addWidget(self.loop_checkbox)
        playback_layout.addWidget(self.position_slider, 1)
        playback_layout.addWidget(volume_icon)
        playback_layout.addWidget(self.volume_slider)

        trim_controls_frame = QFrame()
        trim_controls_frame.setObjectName("TrimFrame")
        trim_controls_layout = QVBoxLayout(trim_controls_frame)
        trim_controls_layout.addWidget(QLabel("Trimming Station", alignment=Qt.AlignCenter))
        
        time_edit_layout = QHBoxLayout()
        self.time_edit_start = QLineEdit("00:00.000")
        self.time_edit_start.editingFinished.connect(self.set_start_time_from_text)
        self.time_edit_end = QLineEdit("00:00.000")
        self.time_edit_end.editingFinished.connect(self.set_end_time_from_text)
        time_edit_layout.addWidget(QLabel("Start:"))
        time_edit_layout.addWidget(self.time_edit_start)
        time_edit_layout.addWidget(QLabel("End:"))
        time_edit_layout.addWidget(self.time_edit_end)

        time_buttons_layout = QHBoxLayout()
        btn_set_start = QPushButton("Set Start [")
        btn_set_start.clicked.connect(self.set_start_time_from_playhead)
        btn_set_end = QPushButton("Set End ]")
        btn_set_end.clicked.connect(self.set_end_time_from_playhead)
        time_buttons_layout.addWidget(btn_set_start)
        time_buttons_layout.addWidget(btn_set_end)

        self.btn_trim = QPushButton("Apply Trim and Cache")
        self.btn_trim.clicked.connect(self.trim_media)
        self.btn_trim.setEnabled(False)
        trim_controls_layout.addLayout(time_edit_layout)
        trim_controls_layout.addLayout(time_buttons_layout)
        trim_controls_layout.addWidget(self.btn_trim)
        
        viewer_layout.addWidget(self.lbl_media_name)
        viewer_layout.addWidget(self.video_widget, 1)
        viewer_layout.addWidget(self.lbl_big_timestamp)
        viewer_layout.addWidget(playback_controls)
        viewer_layout.addWidget(trim_controls_frame)

        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.media_player.playbackStateChanged.connect(self.media_state_changed)

        # --- Right Pane: Cached/Processed Files ---
        cache_frame = QFrame()
        cache_frame.setFrameShape(QFrame.StyledPanel)
        cache_layout = QVBoxLayout(cache_frame)
        
        cache_top_controls = QHBoxLayout()
        cache_top_controls.addWidget(QLabel("Processed Cache"))
        cache_top_controls.addStretch()
        btn_cache_details = QPushButton()
        btn_cache_details.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        btn_cache_details.clicked.connect(lambda: self.set_cache_view_mode("details"))
        btn_cache_thumbs = QPushButton()
        btn_cache_thumbs.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIconView))
        btn_cache_thumbs.clicked.connect(lambda: self.set_cache_view_mode("thumbnails"))
        cache_top_controls.addWidget(btn_cache_details)
        cache_top_controls.addWidget(btn_cache_thumbs)
        cache_layout.addLayout(cache_top_controls)

        self.cache_list = DraggableListWidget()
        self.cache_list.itemSelectionChanged.connect(self.on_cache_selection_changed)
        self.cache_list.itemDoubleClicked.connect(self.on_cache_item_selected)
        
        cache_bottom_controls = QHBoxLayout()
        self.btn_rename_cache = QPushButton("Rename")
        self.btn_rename_cache.clicked.connect(self.rename_cache_item)
        self.btn_delete_cache = QPushButton("Delete")
        self.btn_delete_cache.clicked.connect(self.delete_cache_item)
        cache_bottom_controls.addWidget(self.btn_rename_cache)
        cache_bottom_controls.addWidget(self.btn_delete_cache)
        
        cache_layout.addWidget(self.cache_list)
        cache_layout.addLayout(cache_bottom_controls)

        main_splitter.addWidget(explorer_frame)
        main_splitter.addWidget(viewer_frame)
        main_splitter.addWidget(cache_frame)
        main_splitter.setSizes([350, 750, 300])
        self.on_cache_selection_changed() # Set initial state

    # --- View Mode Management ---
    def apply_view_modes(self):
        self.set_library_view_mode(self.library_view_mode, save=False)
        self.set_cache_view_mode(self.cache_view_mode, save=False)

    def set_library_view_mode(self, mode, save=True):
        self.library_view_mode = mode
        if mode == "details":
            self.tree_view.setIconSize(QSize(24, 24))
        else: # thumbnails
            self.tree_view.setIconSize(QSize(64, 64))
        if save: self.save_config()

    def set_cache_view_mode(self, mode, save=True):
        self.cache_view_mode = mode
        if mode == "details":
            self.cache_list.setViewMode(QListWidget.ListMode)
            self.cache_list.setIconSize(QSize(32, 32))
        else: # thumbnails
            self.cache_list.setViewMode(QListWidget.IconMode)
            self.cache_list.setIconSize(QSize(128, 72))
        if save: self.save_config()


    # --- Library Management ---
    def add_library(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Library Folder")
        if folder_path and folder_path not in self.library_paths:
            self.library_paths.append(folder_path)
            self.save_config()
            self.populate_libraries()
    
    def remove_library(self):
        proxy_index = self.tree_view.currentIndex()
        if not proxy_index.isValid(): return
        source_index = self.proxy_model.mapToSource(proxy_index)
        item = self.library_model.itemFromIndex(source_index)
        while item and item.parent(): item = item.parent()
        if item:
            path_to_remove = item.data(Qt.UserRole)
            if path_to_remove in self.library_paths:
                self.library_paths.remove(path_to_remove)
                self.save_config()
                self.populate_libraries()

    def populate_libraries(self):
        self.library_model.clear()
        self.library_model.setHorizontalHeaderLabels(['Asset Libraries'])
        root_node = self.library_model.invisibleRootItem()
        for path in self.library_paths:
            if os.path.isdir(path):
                lib_item = QStandardItem(f"📁 {os.path.basename(path)}")
                lib_item.setData(path, Qt.UserRole)
                lib_item.setEditable(False)
                root_node.appendRow(lib_item)
                self.populate_directory(lib_item, path)

    def populate_directory(self, parent_item, dir_path):
        try:
            for entry in os.scandir(dir_path):
                item = QStandardItem(entry.name)
                item.setData(entry.path, Qt.UserRole)
                item.setEditable(False)
                if entry.is_dir():
                    item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                    parent_item.appendRow(item)
                    self.populate_directory(item, entry.path)
                else:
                    file_lower = entry.name.lower()
                    is_video = any(file_lower.endswith(ext) for ext in self.VIDEO_EXTENSIONS)
                    is_audio = any(file_lower.endswith(ext) for ext in self.AUDIO_EXTENSIONS)

                    if is_video:
                        item.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
                        if self.ffmpeg_path: self.request_thumbnail(item, entry.path)
                    elif is_audio:
                        item.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
                    else:
                        item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
                    
                    parent_item.appendRow(item)

        except OSError as e: print(f"Error scanning directory {dir_path}: {e}")

    # --- Thumbnail Generation ---
    def request_thumbnail(self, item, media_path):
        base_name = os.path.basename(media_path)
        thumb_filename = f"{pathlib.Path(base_name).stem}.jpg"
        thumb_path = os.path.join(self.thumb_cache_dir, thumb_filename)
        
        worker = ThumbnailGenerator(item, media_path, thumb_path, self.ffmpeg_path)
        worker.thumbnailReady.connect(self.on_thumbnail_ready)
        self.thumbnail_workers.append(worker)
        worker.start()

    @Slot(object, QIcon)
    def on_thumbnail_ready(self, item, icon):
        if item:
            item.setIcon(icon)

    # --- Cache Management ---
    def load_cache(self):
        self.cache_list.clear()
        if not os.path.exists(self.cache_dir): return
        for filename in os.listdir(self.cache_dir):
            if any(filename.lower().endswith(ext) for ext in self.SUPPORTED_MEDIA_TYPES):
                self.add_to_cache_list(os.path.join(self.cache_dir, filename), from_load=True)
    
    @Slot()
    def on_cache_selection_changed(self):
        is_selected = len(self.cache_list.selectedItems()) > 0
        self.btn_rename_cache.setEnabled(is_selected)
        self.btn_delete_cache.setEnabled(is_selected)

    @Slot()
    def rename_cache_item(self):
        selected_items = self.cache_list.selectedItems()
        if not selected_items: return
        item = selected_items[0]
        
        old_path = item.data(Qt.UserRole)
        old_name = os.path.basename(old_path)
        
        new_name, ok = QInputDialog.getText(self, "Rename File", "Enter new name:", QLineEdit.Normal, old_name)
        
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            try:
                os.rename(old_path, new_path)
                item.setText(new_name)
                item.setData(Qt.UserRole, new_path)
            except OSError as e:
                QMessageBox.critical(self, "Rename Error", f"Could not rename file: {e}")

    @Slot()
    def delete_cache_item(self):
        selected_items = self.cache_list.selectedItems()
        if not selected_items: return
        item = selected_items[0]

        reply = QMessageBox.question(self, 'Delete Confirmation', f"Are you sure you want to permanently delete {item.text()}?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            file_path = item.data(Qt.UserRole)

            if self.current_media_path == file_path:
                self.clear_player_state()

            try:
                os.remove(file_path)
                self.cache_list.takeItem(self.cache_list.row(item))
            except OSError as e:
                QMessageBox.critical(self, "Delete Error", f"Could not delete file: {e}")

    @Slot(QListWidgetItem)
    def on_cache_item_selected(self, item):
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.isfile(file_path):
            self.load_media(file_path)

    # --- UI Logic and Slots ---
    @Slot(str)
    def on_search_text_changed(self, text):
        self.proxy_model.setFilterRegularExpression(text)

    @Slot(QModelIndex)
    def on_file_selected(self, proxy_index):
        source_index = self.proxy_model.mapToSource(proxy_index)
        item = self.library_model.itemFromIndex(source_index)
        if item:
            file_path = item.data(Qt.UserRole)
            if file_path and os.path.isfile(file_path):
                self.load_media(file_path)

    def load_media(self, file_path):
        self.clear_player_state()
        self.loop_checkbox.setChecked(False)
        self.current_media_path = file_path
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.lbl_media_name.setText(os.path.basename(file_path))
        self.btn_play.setEnabled(True)
        self.btn_trim.setEnabled(self.ffmpeg_path is not None)
        self.play_media()

    def clear_player_state(self):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.current_media_path = None
        self.lbl_media_name.setText("No Media Loaded")
        self.lbl_big_timestamp.setText("00:00.000 / 00:00.000")
        self.btn_play.setEnabled(False)
        self.btn_trim.setEnabled(False)
        self.reset_trim_times()


    def play_media(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.media_player.pause()
        else: self.media_player.play()

    def media_state_changed(self, state):
        icon = QStyle.SP_MediaPause if state == QMediaPlayer.PlaybackState.PlayingState else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon))
    
    def position_changed(self, position):
        self.position_slider.setPosition(position)
        self.lbl_big_timestamp.setText(f"{self.format_time(position)} / {self.format_time(self.media_player.duration())}")
        if (self.loop_checkbox.isChecked() and
            self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and
            self.end_time_ms > self.start_time_ms and
            position >= self.end_time_ms):
            if abs(position - self.end_time_ms) < 100:
                self.media_player.setPosition(self.start_time_ms)
    
    def duration_changed(self, duration):
        duration = duration if duration > 0 else 0
        self.position_slider.setRange(0, duration)
        self.reset_trim_times()
        self.lbl_big_timestamp.setText(f"00:00.000 / {self.format_time(duration)}")

    @Slot(int)
    def set_position(self, position):
        self.media_player.setPosition(position)
        
    @Slot()
    def on_slider_pressed(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.was_playing_before_drag = True
            self.media_player.pause()
        else:
            self.was_playing_before_drag = False

    @Slot()
    def on_slider_released(self):
        if self.was_playing_before_drag:
            self.media_player.play()
        self.was_playing_before_drag = False


    def format_time(self, ms):
        if ms < 0: ms = 0
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        return f"{int(m):02d}:{int(s):02d}.{int(ms):03d}"
    
    def parse_time(self, time_str):
        match = re.match(r'(\d{1,2}):(\d{2})\.(\d{3})', time_str)
        if match:
            m, s, ms = map(int, match.groups())
            return (m * 60 + s) * 1000 + ms
        return None

    def reset_trim_times(self):
        duration = self.media_player.duration()
        self.start_time_ms, self.end_time_ms = 0, duration
        self.position_slider.setStartMarker(0)
        self.position_slider.setEndMarker(duration)
        self.time_edit_start.setText(self.format_time(0))
        self.time_edit_end.setText(self.format_time(duration))

    def set_start_time_from_playhead(self):
        pos = self.media_player.position()
        if pos < self.end_time_ms:
            self.start_time_ms = pos
            self.position_slider.setStartMarker(pos)
            self.time_edit_start.setText(self.format_time(pos))

    def set_end_time_from_playhead(self):
        pos = self.media_player.position()
        if pos > self.start_time_ms:
            self.end_time_ms = pos
            self.position_slider.setEndMarker(pos)
            self.time_edit_end.setText(self.format_time(pos))

    @Slot(int)
    def set_start_time_from_slider(self, value):
        self.start_time_ms = value
        self.time_edit_start.setText(self.format_time(value))
        self.position_slider.setStartMarker(value) # Ensure UI sync

    @Slot(int)
    def set_end_time_from_slider(self, value):
        self.end_time_ms = value
        self.time_edit_end.setText(self.format_time(value))
        self.position_slider.setEndMarker(value) # Ensure UI sync
    
    @Slot()
    def set_start_time_from_text(self):
        new_start_ms = self.parse_time(self.time_edit_start.text())
        if new_start_ms is not None and new_start_ms < self.end_time_ms:
            self.start_time_ms = new_start_ms
            self.position_slider.setStartMarker(new_start_ms)
        else:
            self.time_edit_start.setText(self.format_time(self.start_time_ms))
    
    @Slot()
    def set_end_time_from_text(self):
        new_end_ms = self.parse_time(self.time_edit_end.text())
        if new_end_ms is not None and new_end_ms > self.start_time_ms:
            self.end_time_ms = new_end_ms
            self.position_slider.setEndMarker(new_end_ms)
        else:
            self.time_edit_end.setText(self.format_time(self.end_time_ms))

    def keyPressEvent(self, event):
        key = event.key()
        frame_duration_ms = 33 # Approx 1 frame at 30fps
        current_pos = self.media_player.position()
        
        if key == Qt.Key_Right:
            self.media_player.setPosition(current_pos + frame_duration_ms)
        elif key == Qt.Key_Left:
            self.media_player.setPosition(max(0, current_pos - frame_duration_ms))
        else:
            super().keyPressEvent(event)
            
    @Slot(int)
    def set_volume(self, value):
        self.volume = value
        self.audio_output.setVolume(value / 100.0)

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)

    def trim_media(self):
        if not self.current_media_path: return
        if self.start_time_ms >= self.end_time_ms:
            QMessageBox.warning(self, "Trim Error", "Start time must be before end time.")
            return
        self.media_player.pause()
        input_path = pathlib.Path(self.current_media_path)
        output_filename = f"{input_path.stem}_trimmed_{self.start_time_ms}_{self.end_time_ms}{input_path.suffix}"
        output_path = os.path.join(self.cache_dir, output_filename)
        
        command = [
            self.ffmpeg_path, '-i', str(input_path), 
            '-ss', str(self.start_time_ms / 1000.0),
            '-to', str(self.end_time_ms / 1000.0), 
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', # Re-encode for compatibility
            '-y', output_path
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            self.add_to_cache_list(output_path)
            QMessageBox.information(self, "Trim Success", f"File successfully cached.")
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "FFmpeg Error", f"An error occurred during trimming.\n\nError:\n{e.stderr}")

    def add_to_cache_list(self, file_path, from_load=False):
        base_name = os.path.basename(file_path)
        if not self.cache_list.findItems(base_name, Qt.MatchFixedString):
            item = QListWidgetItem(base_name)
            item.setData(Qt.UserRole, file_path)
            
            file_lower = base_name.lower()
            if any(file_lower.endswith(ext) for ext in self.VIDEO_EXTENSIONS):
                item.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay)) # Placeholder
                if self.ffmpeg_path: self.request_thumbnail(item, file_path)
            else:
                item.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))

            self.cache_list.addItem(item)
            
    def get_stylesheet(self):
        return """
        QMainWindow, QWidget { background-color: #2b2b2b; color: #dcdcdc; font-family: 'Segoe UI', Arial, sans-serif; }
        QTreeView, QListWidget, QLineEdit { background-color: #3c3f41; border: 1px solid #555555; border-radius: 4px; font-size: 14px; padding: 5px; color: #dcdcdc; }
        QTreeView::item { padding: 4px; }
        QTreeView::item:hover, QListWidget::item:hover { background-color: #4b4f52; }
        QTreeView::item:selected, QListWidget::item:selected { background-color: #007acc; color: #ffffff; }
        QPushButton { background-color: #007acc; color: white; border: none; padding: 10px 15px; border-radius: 4px; font-size: 14px; font-weight: bold; }
        QPushButton:hover { background-color: #005f9e; }
        QPushButton:pressed { background-color: #004c7d; }
        QPushButton:disabled { background-color: #555555; color: #888888; }
        QLabel { font-size: 14px; padding-top: 4px; color: #dcdcdc; }
        QLabel#MediaTitle { font-size: 18px; font-weight: bold; padding: 5px; color: #007acc; }
        QLabel#BigTimestamp { font-size: 48px; font-weight: bold; color: #dcdcdc; qproperty-alignment: 'AlignCenter'; padding: 10px 0; }
        QSplitter::handle { background-color: #555555; }
        QSplitter::handle:horizontal { width: 3px; }
        QFrame, QFrame#TrimFrame { border: 1px solid #3c3f41; border-radius: 5px; padding: 10px; }
        QMessageBox { background-color: #3c3f41; }
        QCheckBox { spacing: 5px; font-size: 14px; padding: 5px; color: #dcdcdc; }
        QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; }
        QCheckBox::indicator:unchecked { background-color: #3c3f41; border: 1px solid #777777; }
        QCheckBox::indicator:checked { background-color: #007acc; border: 1px solid #005f9e; }
        QSlider::groove:horizontal {
            border: 1px solid #555555;
            height: 4px;
            background: #4f4f4f;
            margin: 2px 0;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #dcdcdc;
            border: 1px solid #555555;
            width: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }
        QSlider::sub-page:horizontal {
            background: #007acc;
            border: 1px solid #555555;
            height: 4px;
            border-radius: 2px;
        }
        """
# --- Application Entry Point ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

