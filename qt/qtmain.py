import sys
import os
import cv2
import numpy as np
from time import strftime, time, sleep
from threading import Thread, Lock, Event
import random
import json

from matplotlib.backends.qt_compat import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import (FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure

from PyQt5.QtWidgets import QApplication, QMessageBox, QInputDialog, QWidget, QPushButton, QSizePolicy
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5 import QtGui, QtCore
from functools import partial
from PyQt5.QtCore import QSize, QFile, QTextStream, QUrl
from PyQt5.QtQuick import QQuickView

from flyrpc.launch import launch_server
from flyvr.service import Service

from flyvr.cnc import CncThread, cnc_home
from flyvr.camera import CamThread
from flyvr.tracker import TrackThread, ManualVelocity
from flyvr.dispenser import FlyDispenser
from flyvr.opto import OptoThread
from flyvr.stim import StimThread
from flyvr.trial import TrialThread
from qt.plotting import PlotWindow, ImgWindow
from qt.gui import GuiThread
from rangeslider import QRangeSlider

class MainGui():
    def __init__(self, dialog):

        self.ui = uic.loadUi('main.ui')
        self.ui.show()

        #self.left = 600
        #self.top = 400

        # Set services to none
        self.dispenser = None
        self.opto = None
        self._cam = None
        self.stim = None

        # Set background services to none
        self.trial = None
        self.tracker = None

        self.cam_view = None
        self.dispenser_view = None
        self.frameData = None
        self.centermarked = None

        self.cnc_shouldinitialize = None
        self.message = []
        self.trial_duration = None
        self.inter_fly_wait = None
        self.max_inter_fly_wait = 10 * 60 # min*sec
        self.turn_off_time = 2 * 60 * 60 # hr*min*sec

        # Fly detection parameters
        self.ma_min = 0.2  # mm
        self.ma_max = 2.0  # mm
        self.MA_min = 0.6  # mm
        self.MA_max = 5.0  # mm
        self.r_min = 0.20
        self.r_max = 0.80

        # Setup fly detection range sliders
        self.configure_range_sliders()
        self.ui.ar_min_label.setText('{:0.2f}{}'.format(self.r_min,'    '))
        self.ui.ar_max_label.setText('{:0.2f}{}'.format(self.r_max,'    '))
        self.ui.ma_min_label.setText('{:0.1f}{}'.format(self.ma_min,'mm'))
        self.ui.ma_max_label.setText('{:0.1f}{}'.format(self.ma_max,'mm'))
        self.ui.MA_min_label.setText('{:0.1f}{}'.format(self.MA_min,'mm'))
        self.ui.MA_max_label.setText('{:0.1f}{}'.format(self.MA_max,'mm'))

        # Setup cnc buttons
        self.ui.cnc_start_button.clicked.connect(lambda x: self.trackerStart())
        self.ui.cnc_stop_button.clicked.connect(lambda x: self.trackerStop())
        self.ui.cnc_initialize_button.clicked.connect(lambda x: self.tracker.cnc_shouldinitialize.set())
        self.ui.cnc_move_center_button.clicked.connect(lambda x: self.tracker.start_moving_to_center())
        self.ui.cnc_mark_center_button.clicked.connect(lambda x: self.markCenter())
        self.ui.cnc_initialize_button.setEnabled(False)
        self.ui.cnc_move_center_button.setEnabled(False)
        self.ui.cnc_mark_center_button.setEnabled(False)

        # Setup cnc movement buttons
        self.ui.cnc_up_button.pressed.connect(lambda: self.tracker.manual_move_up())
        self.ui.cnc_up_button.released.connect(lambda: self.tracker.manual_stop())
        self.ui.cnc_down_button.pressed.connect(lambda: self.tracker.manual_move_down())
        self.ui.cnc_down_button.released.connect(lambda: self.tracker.manual_stop())
        self.ui.cnc_right_button.pressed.connect(lambda: self.tracker.manual_move_right())
        self.ui.cnc_right_button.released.connect(lambda: self.tracker.manual_stop())
        self.ui.cnc_left_button.pressed.connect(lambda: self.tracker.manual_move_left())
        self.ui.cnc_left_button.released.connect(lambda: self.tracker.manual_stop())
        self.ui.cnc_up_button.setEnabled(False)
        self.ui.cnc_down_button.setEnabled(False)
        self.ui.cnc_left_button.setEnabled(False)
        self.ui.cnc_right_button.setEnabled(False)

        # Setup cam buttons
        self.ui.camera_start_button.clicked.connect(lambda x: self.camStart())
        self.ui.camera_stop_button.clicked.connect(lambda x: self.camStop())

        # Setup dispenser buttons
        self.ui.dispenser_start_button.clicked.connect(lambda x: self.dispenserStart())
        self.ui.dispenser_stop_button.clicked.connect(lambda x: self.dispenserStop())
        self.ui.open_gate_button.clicked.connect(lambda x: self.openDispenser())
        self.ui.close_gate_button.clicked.connect(lambda x: self.closeDispenser())
        self.ui.calibrate_gate_button.clicked.connect(lambda x: self.calibrateDispenser())
        self.ui.close_gate_button.setEnabled(False)
        self.ui.open_gate_button.setEnabled(False)
        self.ui.calibrate_gate_button.setEnabled(False)
        self.ui.gate_label_closed.hide()
        self.ui.gate_label_open.hide()

        # Setup opto buttons
        self.ui.opto_start_button.clicked.connect(lambda x: self.optoStart())
        self.ui.opto_stop_button.clicked.connect(lambda x: self.optoStop())
        self.ui.opto_on_button.clicked.connect(lambda x: self.opto.on())
        self.ui.opto_off_button.clicked.connect(lambda x: self.opto.off())
        self.ui.opto_pulse_button.clicked.connect(lambda x: self.opto.pulse())
        self.ui.opto_foraging_button.clicked.connect(lambda x: self.foraging())
        self.ui.opto_foraging_button.setEnabled(False)
        self.ui.opto_stop_button.setEnabled(False)
        self.ui.opto_on_button.setEnabled(False)
        self.ui.opto_off_button.setEnabled(False)
        self.ui.opto_pulse_button.setEnabled(False)
        self.ui.opto_label_off.hide()
        self.ui.opto_label_on.hide()

        # Setup main experiment buttons
        self.ui.start_experiment_button.clicked.connect(lambda x: self.experimentStart())
        self.ui.stop_experiment_button.clicked.connect(lambda x: self.experimentStop())

        # Setup trial buttons
        self.ui.start_trial_button.clicked.connect(lambda x: self.trialStart())
        self.ui.stop_trial_button.clicked.connect(lambda x: self.trialStop())
        self.ui.start_trial_button.setEnabled(False)
        self.ui.stop_trial_button.setEnabled(False)

        # Setup camera sliders
        self.ui.thresh_slider.setValue(200)
        self.ui.thresh_label.setText(str(self.ui.thresh_slider.value()))
        #self.ui.r_min_slider.setValue(2)
        #self.ui.r_min_label.setText(str(self.ui.r_min_slider.value()))
        #self.ui.r_max_slider.setValue(8)
        #self.ui.r_max_label.setText(str(self.ui.r_max_slider.value()))
        self.ui.loop_gain_slider.setValue(80)
        self.ui.loop_gain_label.setText(str(self.ui.loop_gain_slider.value()))
        self.ui.thresh_slider.valueChanged.connect(self.thresholdChange)
        #self.ui.r_min_slider.valueChanged.connect(self.rminChange)
        #self.ui.r_max_slider.valueChanged.connect(self.rmaxChange)
        self.ui.loop_gain_slider.valueChanged.connect(self.loopgainChange)

        # Setup camera checkboxes
        #self.ui.image_type_combo.setEnabled(False)
        #self.ui.image_type_combo.activated[str].connect(self.image_type)
        self.ui.draw_contours_checkbox.setChecked(True)
        self.ui.draw_contours_checkbox.setEnabled(False)

        self.ui.show_threshold_checkbox.setChecked(False)
        self.ui.show_threshold_checkbox.setEnabled(False)

        self.ui.closed_loop_pos.setChecked(False)
        self.ui.closed_loop_pos.setEnabled(True)

        self.ui.closed_loop_angle.setChecked(False)
        self.ui.closed_loop_angle.setEnabled(True)

        self.ui.show_threshold_checkbox.stateChanged.connect(lambda x: self.camThreshold())
        self.ui.draw_contours_checkbox.stateChanged.connect(lambda x: self.camContours())
        self.ui.closed_loop_pos.stateChanged.connect(lambda x: self.closed_loop_pos_checked())
        self.ui.closed_loop_angle.stateChanged.connect(lambda x: self.closed_loop_angle_checked())

        # Setup metadata input
        self.ui.save_metadata_button.clicked.connect(lambda x: self.saveMetadata())
        self.ui.save_metadata_button.setEnabled(False)

        # Setup visual stimuli buttons
        self.ui.stim_start_button.clicked.connect(lambda x: self.stimStart())
        self.ui.stim_per_trial_button.clicked.connect(lambda x: self.stimPerTrial())
        self.ui.stim_within_trial_button.clicked.connect(lambda x: self.stimWithinTrial())
        self.ui.multi_stim_within_trial_button.clicked.connect(lambda x: self.multiStimWithinTrial())
        self.ui.stim_per_trial_button.setEnabled(False)
        self.ui.stim_within_trial_button.setEnabled(False)
        self.ui.multi_stim_within_trial_button.setEnabled(False)

        # Create timers for displaying parameters on gui for user to see
        self.camera_timer = None
        self.cnc_timer = None
        self.exp_data_timer = None
        self.dispenser_data_timer = None
        self.opto_timer = None

        self.trial_timer = QtCore.QTimer()
        self.trial_timer.timeout.connect(self.trialTimer)
        self.trial_timer.start(100)

        self.light_checker_timer = QtCore.QTimer()
        self.light_checker_timer.timeout.connect(self.gui_update_lights)
        self.light_checker_timer.start(100)

        # Setup fly position plotter
        self.ui.fly_position_plot_button.clicked.connect(lambda x: self.flyPlotter())

    def configure_range_sliders(self):
        self.ar_range = QRangeSlider(self.ui)
        self.ma_range = QRangeSlider(self.ui)
        self.MA_range = QRangeSlider(self.ui)

        self.ar_range.setMin(0)
        self.ar_range.setMax(102)
        self.ar_range.setRange(int(self.r_min * 100), int(self.r_max * 100))
        self.ar_range.setDrawValues(False)
        self.ar_range.startValueChanged.connect(self.rminChange)
        self.ar_range.endValueChanged.connect(self.rmaxChange)

        self.ma_range.setMin(0)
        self.ma_range.setMax(102)
        self.ma_range.setRange(int(self.ma_min * 10), int(self.ma_max * 10))
        self.ma_range.setDrawValues(False)
        self.ma_range.startValueChanged.connect(self.ma_min_change)
        self.ma_range.endValueChanged.connect(self.ma_max_change)

        self.MA_range.setMin(0)
        self.MA_range.setMax(102)
        self.MA_range.setRange(int(self.MA_min * 10), int(self.MA_max * 10))
        self.MA_range.setDrawValues(False)
        self.MA_range.startValueChanged.connect(self.MA_min_change)
        self.MA_range.endValueChanged.connect(self.MA_max_change)

        self.ui.ar_grid.addWidget(self.ar_range, 1, 1, 1, 1)
        self.ui.ma_grid.addWidget(self.ma_range, 1, 1, 1, 1)
        self.ui.MA_grid.addWidget(self.MA_range, 1, 1, 1, 1)
        self.ar_range.setEnabled(False)
        self.ma_range.setEnabled(False)
        self.MA_range.setEnabled(False)

    @property
    def cnc(self):
        try:
            return self.tracker.cnc
        except:
            return None

    @property
    def cncinit(self):
        try:
            return self.tracker.is_init
        except:
            return False

    @property
    def cam(self):
        return self._cam

    @cam.setter
    def cam(self, value):
        self._cam = value
        try:
            self.tracker.camThread = value
        except:
            pass

    def camThreshold(self):
        if self.cam is not None:
            if self.ui.show_threshold_checkbox.isChecked():
                self.cam.show_threshold = True
            else:
                self.cam.show_threshold = False

    def camContours(self):
        if self.cam is not None:
            if self.ui.draw_contours_checkbox.isChecked():
                self.cam.draw_contours = True
            else:
                self.cam.draw_contours = False

    def stimPerTrial(self):
        self.stim.mode = 'single_stim'

    def stimWithinTrial(self):
        self.stim.mode = 'multi_rotation'
        self.stim.pause_duration = 2.0
        self.stim.stim_duration = 2.0

    def multiStimWithinTrial(self):
        self.stim.mode = 'multi_stim'
        self.stim.stim_duration = 20.0

    def stimStart(self):
        self.stim = StimThread()
        self.ui.stim_stop_button.setEnabled(True)
        self.ui.stim_start_button.setEnabled(False)
        self.ui.stim_per_trial_button.setEnabled(True)
        self.ui.stim_within_trial_button.setEnabled(True)
        self.ui.multi_stim_within_trial_button.setEnabled(True)

    def pretty_json(self, d):
        return json.dumps(d, indent=2, sort_keys=False)

    def saveMetadata(self):
        user = self.ui.user_textbox.text()
        age = self.ui.age_textbox.text()
        timezone = self.ui.timezone_textbox.text()
        genotype = self.ui.genotype_textbox.text()

        d = {'user': user, 'age': age, 'timezone': timezone, 'genotype': genotype}
        data = self.pretty_json(d)

        exp_dir = None
        try:
            exp_dir = self.trial.exp_dir
        except:
            pass

        if exp_dir is not None:
            fname = os.path.join(exp_dir, 'metadata.txt')
            with open(fname, 'w') as f:
                f.write(data)

    def thresholdChange(self):
        value = self.ui.thresh_slider.value()
        self.ui.thresh_label.setText(str(value))
        self.cam.threshold = value

    def rminChange(self, val):
        self.ui.ar_min_label.setText('{:0.2f}'.format(val / 100))

        try:
            self.cam.cam.r_min = val/100
        except:
            pass

    def rmaxChange(self, val):
        self.ui.ar_max_label.setText('{:0.2f}'.format(val / 100))

        try:
            self.cam.cam.r_max = val/100
        except:
            pass

    def ma_min_change(self, val):
        self.ui.ma_min_label.setText('{:0.1f}{}'.format(val / 10, 'mm'))

        try:
            self.cam.cam.ma_min = val * 1e-4
        except:
            pass

    def ma_max_change(self, val):
        self.ui.ma_max_label.setText('{:0.1f}{}'.format(val / 10, 'mm'))

        try:
            self.cam.cam.ma_max = val * 1e-4
        except:
            pass

    def MA_min_change(self, val):
        self.ui.MA_min_label.setText('{:0.1f}{}'.format(val / 10, 'mm'))

        try:
            self.cam.cam.MA_min = val * 1e-4
        except:
            pass

    def MA_max_change(self, val):
        self.ui.MA_max_label.setText('{:0.1f}{}'.format(val / 10, 'mm'))

        try:
            self.cam.cam.MA_max = val * 1e-4
        except:
            pass


    def loopgainChange(self):
        value = self.ui.loop_gain_slider.value()
        self.ui.loop_gain_label.setText(str(value))
        self.tracker.a = value/10.0

    def dispenserStart(self):
        self.dispenser = FlyDispenser()
        self.dispenser.start()
        self.dispenser_view = DispenserView(self.dispenser)
        self.ui.dispenser_start_button.setEnabled(False)
        self.ui.dispenser_stop_button.setEnabled(True)
        self.ui.close_gate_button.setEnabled(True)
        self.ui.open_gate_button.setEnabled(True)
        self.ui.calibrate_gate_button.setEnabled(True)

        self.dispenser_data_timer = QtCore.QTimer()
        self.dispenser_data_timer.timeout.connect(self.gui_dispenser_info)
        self.dispenser_data_timer.start(100)

    def dispenserStop(self):
        self.dispenser_view.close()
        self.dispenser.stop()
        self.dispenser = None
        self.ui.dispenser_start_button.setEnabled(True)
        self.ui.dispenser_stop_button.setEnabled(False)
        self.ui.close_gate_button.setEnabled(False)
        self.ui.open_gate_button.setEnabled(False)
        self.ui.calibrate_gate_button.setEnabled(False)

        if self.dispenser_data_timer is not None:
            self.dispenser_data_timer.stop()

        self.ui.dispenser_status_label.setText('N/A')

    def openDispenser(self):
        self.dispenser.open_gate()

    def closeDispenser(self):
        self.dispenser.close_gate()

    def calibrateDispenser(self):
        self.dispenser.calibrate_gate()

    def trackerStart(self):
        # find if we should initialize
        mail = Mail()
        CncPopup(mail)
        cnc_shouldinitialize = mail.message

        # start tracker
        self.tracker = TrackThread(camThread=self.cam)

        if cnc_shouldinitialize:
            self.tracker.cnc_shouldinitialize.set()

        self.tracker.start()

        # set status of UI buttons
        self.ui.cnc_up_button.setEnabled(True)
        self.ui.cnc_down_button.setEnabled(True)
        self.ui.cnc_left_button.setEnabled(True)
        self.ui.cnc_right_button.setEnabled(True)
        self.ui.cnc_start_button.setEnabled(False)
        self.ui.cnc_stop_button.setEnabled(True)
        self.ui.cnc_initialize_button.setEnabled(True)
        self.ui.cnc_move_center_button.setEnabled(True)
        self.ui.cnc_mark_center_button.setEnabled(True)

        self.cnc_timer = QtCore.QTimer()
        self.cnc_timer.timeout.connect(self.gui_update_cnc)
        self.cnc_timer.start(100)

    def gui_update_cnc(self):
        try:
            cnc_status = self.tracker.cncThread.status
        except:
            return

        if cnc_status is not None:
            self.ui.cnc_x_label.setText('{:0.3f}'.format(cnc_status.posX))
            self.ui.cnc_y_label.setText('{:0.3f}'.format(cnc_status.posY))
        else:
            self.reset_cnc_data()

    def reset_cnc_data(self):
        self.ui.cnc_x_label.setText('N/A')
        self.ui.cnc_y_label.setText('N/A')

    def trackerStop(self):
        self.tracker.stop()
        self.tracker = None

        # set status of UI buttons
        self.ui.cnc_up_button.setEnabled(False)
        self.ui.cnc_down_button.setEnabled(False)
        self.ui.cnc_left_button.setEnabled(False)
        self.ui.cnc_right_button.setEnabled(False)
        self.ui.cnc_start_button.setEnabled(True)
        self.ui.cnc_stop_button.setEnabled(False)
        self.ui.cnc_initialize_button.setEnabled(False)
        self.ui.cnc_move_center_button.setEnabled(False)
        self.ui.cnc_mark_center_button.setEnabled(False)

        if self.cnc_timer is not None:
            self.cnc_timer.stop()

        self.reset_cnc_data()

    def markCenter(self):
        self.tracker.mark_center()
        self.centermarked = True

    def camStart(self):
        self.cam = CamThread()
        self.cam.start()
        self.cam.ma_min = self.ma_min * 1e-3,
        self.cam.ma_max = self.ma_max * 1e-3,
        self.cam.MA_min = self.MA_min * 1e-3,
        self.cam.MA_max = self.MA_max * 1e-3,
        self.cam.r_min = self.r_min,
        self.cam.r_max = self.r_max
        self.cam_view = CameraView(self.cam)

        self.ui.camera_start_button.setEnabled(False)
        self.ui.camera_stop_button.setEnabled(True)
        self.ui.draw_contours_checkbox.setEnabled(True)
        self.ui.show_threshold_checkbox.setEnabled(True)
        self.ar_range.setEnabled(True)
        self.ma_range.setEnabled(True)
        self.MA_range.setEnabled(True)

        self.camera_timer = QtCore.QTimer()
        self.camera_timer.timeout.connect(self.gui_update_camera)
        self.camera_timer.start(100)

    def gui_update_camera(self):
        try:
            fly_data = self.cam.flyData
        except:
            return

        if fly_data is not None and fly_data.flyPresent:
            self.ui.fly_minor_axis_label.setText('{:0.2f}'.format(fly_data.ma*1e3))
            self.ui.fly_major_axis_label.setText('{:0.2f}'.format(fly_data.MA*1e3))
            self.ui.fly_aspect_ratio_label.setText('{:0.2f}'.format(fly_data.aspect_ratio))
            self.ui.fly_x_label.setText('{:0.2f}'.format(fly_data.flyX*1e3))
            self.ui.fly_y_label.setText('{:0.2f}'.format(fly_data.flyY*1e3))
            self.ui.fly_angle_label.setText('{:0.1f}'.format(fly_data.angle))
        else:
            self.reset_fly_data()

    def reset_fly_data(self):
        self.ui.fly_minor_axis_label.setText('N/A')
        self.ui.fly_major_axis_label.setText('N/A')
        self.ui.fly_aspect_ratio_label.setText('N/A')
        self.ui.fly_x_label.setText('N/A')
        self.ui.fly_y_label.setText('N/A')
        self.ui.fly_angle_label.setText('N/A')

    def camStop(self):
        self.cam_view.close()

        self.cam.stop()
        self.cam = None

        self.ui.draw_contours_checkbox.setChecked(True)
        self.ui.show_threshold_checkbox.setChecked(False)
        self.ui.camera_start_button.setEnabled(True)
        self.ui.camera_stop_button.setEnabled(False)
        self.ui.draw_contours_checkbox.setEnabled(False)
        self.ui.show_threshold_checkbox.setEnabled(False)
        self.ar_range.setEnabled(False)
        self.ma_range.setEnabled(False)
        self.MA_range.setEnabled(False)

        if self.camera_timer is not None:
            self.camera_timer.stop()

        self.reset_fly_data()

    def optoStart(self):
        self.opto = OptoThread(cncThread=self.tracker.cncThread, camThread=self.cam,
                               trackThread=self.tracker, trialThread = self.trial)
        self.opto.start()
        self.ui.opto_start_button.setEnabled(False)
        self.ui.opto_stop_button.setEnabled(True)
        self.ui.opto_on_button.setEnabled(True)
        self.ui.opto_off_button.setEnabled(True)
        self.ui.opto_pulse_button.setEnabled(True)
        self.ui.opto_foraging_button.setEnabled(True)

        self.opto_timer = QtCore.QTimer()
        self.opto_timer.timeout.connect(self.gui_update_opto)
        self.opto_timer.start(100)

    def optoStop(self):
        self.opto_timer.stop()
        self.opto.off()
        self.opto.stop()
        self.opto = None
        self.ui.opto_start_button.setEnabled(True)
        self.ui.opto_stop_button.setEnabled(False)
        self.ui.opto_on_button.setEnabled(False)
        self.ui.opto_off_button.setEnabled(False)
        self.ui.opto_pulse_button.setEnabled(False)
        self.ui.opto_foraging_button.setEnabled(False)

    def foraging(self):
        self.opto.foraging = True

    def experimentStart(self):
        if self.cam is None:
            self.message.append("Turn on the camera before starting the experiment.")
        if self.tracker is None:
            self.message.append("Turn on the cnc before starting the experiment.")
        if not self.cncinit:
            if not self.centermarked:
                self.message.append("Initialize cnc or mark center before starting the experiment.")
        if self.message:
            print(self.message)
            MessagePopup(self.message)
            self.message = []
        else:
            self.trial = TrialThread(cam=self.cam, dispenser=self.dispenser, tracker=self.tracker,
                                           opto=self.opto, stim=self.stim, ui=self.ui)
            self.trial.start()
            if self.dispenser is not None:
                self.dispenser.release_fly()
            self.ui.start_experiment_button.setEnabled(False)
            self.ui.stop_experiment_button.setEnabled(True)
            self.ui.stop_trial_button.setEnabled(True)
            self.ui.save_metadata_button.setEnabled(True)

            self.exp_data_timer = QtCore.QTimer()
            self.exp_data_timer.timeout.connect(self.gui_update_exp_info)
            self.exp_data_timer.start(100)

    def experimentStop(self):
        self.trial._stop_trial()
        self.trial.stop()
        self.trial = None
        self.ui.start_experiment_button.setEnabled(True)
        self.ui.stop_experiment_button.setEnabled(False)
        self.ui.start_trial_button.setEnabled(False)
        self.ui.stop_trial_button.setEnabled(False)
        self.ui.save_metadata_button.setEnabled(False)

        #if self.exp_data_timer is not None:
        #    self.exp_data_timer.stop()

        #self.ui.experiment_label.setText('N/A')
        #self.ui.trial_num_label.setText('N/A')

    def trialStart(self):
        self.trial._start_trial()
        if self.dispenser is not None:
            self.dispenser.release_fly()
        self.ui.start_trial_button.setEnabled(False)
        self.ui.stop_trial_button.setEnabled(True)
        self.ui.start_experiment_button.setEnabled(False)
        self.ui.stop_experiment_button.setEnabled(True)

    def trialStop(self):
        self.trial._stop_trial()
        if self.dispenser is not None:
            self.dispenser.state = 'Reset'
        self.tracker.start_moving_to_center()
        self.ui.start_trial_button.setEnabled(True)
        self.ui.stop_trial_button.setEnabled(False)
        self.ui.start_experiment_button.setEnabled(False)
        self.ui.stop_experiment_button.setEnabled(False)

    def gui_update_exp_info(self):
        exp = None
        trial_num = None
        trial_start_t = None
        big_rig_status = None

        try:
            exp = self.trial.exp
        except:
            pass

        try:
            trial_num = self.trial.trial_num
        except:
            pass

        try:
            trial_start_t = self.trial.trial_start_t
        except:
            pass

        try:
            big_rig_status = self.trial.state
        except:
            pass

        if exp is not None:
            self.ui.experiment_label.setText('{}'.format(str(exp)))
        else:
            self.ui.experiment_label.setText('N/A')

        if trial_num is not None:
            self.ui.trial_num_label.setText('{}'.format(str(trial_num)))
        else:
            self.ui.trial_num_label.setText('N/A')

        if trial_start_t is not None:
            self.trial_duration = time() - trial_start_t
            mins = int(np.floor(self.trial_duration/60))
            #print('dur:', self.trial_duration)
            #print('floor:', np.floor(self.trial_duration/60))
            #print('mins:', mins)
            if mins == 0:
                mins = '00'
            elif mins < 10:
                mins = '0' + str(mins)
            secs = int(self.trial_duration)%60
            if secs < 10:
                secs = '0' + str(secs)
            self.ui.trial_time_label.setText('{}:{}'.format(str(mins), str(secs)))
        else:
            self.ui.trial_time_label.setText('N/A')

        if big_rig_status is not None:
            self.ui.bigrig_state_label.setText(big_rig_status)
        else:
            self.ui.bigrig_state_label.setText('N/A')

    #def keyPressEvent(self, e):    
    #    if e.key() == Qt.Key_Escape:
    #        self.close()

    def gui_update_lights(self):
        if self.tracker is not None:
            self.ui.cnc_red_light.hide()
        else:
            self.ui.cnc_red_light.show()

        if self.cam is not None:
            self.ui.cam_red_light.hide()
        else:
            self.ui.cam_red_light.show()

        if self.opto is not None:
            self.ui.opto_red_light.hide()
        else:
            self.ui.opto_red_light.show()

        if self.dispenser is not None:
            self.ui.dispenser_red_light.hide()
        else:
            self.ui.dispenser_red_light.show()

        if self.stim is not None:
            self.ui.stim_red_light.hide()
        else:
            self.ui.stim_red_light.show()

    def gui_update_opto(self):
        if self.opto.led_status == 'on':
            self.ui.opto_label_on.show()
            self.ui.opto_label_off.hide()
        elif self.opto.led_status == 'off':
            self.ui.opto_label_off.show()
            self.ui.opto_label_on.hide()

    def gui_dispenser_info(self):
        self.ui.dispenser_status_label.setText(self.dispenser.state)
        if self.dispenser.gate_state == 'open':
            self.ui.gate_label_open.show()
            self.ui.gate_label_closed.hide()
        elif self.dispenser.gate_state == 'closed':
            self.ui.gate_label_closed.show()
            self.ui.gate_label_open.hide()

    def flyPlotter(self):
        if self.cam is None:
            self.message.append("Turn on the camera before starting the plotter.")
        if self.tracker is None:
            self.message.append("Turn on the cnc before starting the plotter.")
        if not self.cncinit:
            if not self.centermarked:
                self.message.append("Initialize cnc or mark center before starting the plotter.")
        if self.message:
            print(self.message)
            MessagePopup(self.message)
            self.message = []
        else:
            self.flypositionwindow = FlyPositionWindow(cam=self.cam, cnc=self.tracker)

    def trialTimer(self):
        self.current_max_inter_fly_wait = self.max_inter_fly_wait
        if self.trial is not None:
            if self.trial.trial_end_t is not None:
                self.inter_fly_wait = self.trial.trial_end_t - time()

                # re-release fly if we've been waiting too long (and keep trying)
                if self.inter_fly_wait > self.current_max_inter_fly_wait:
                    self.current_max_inter_fly_wait = self.current_max_inter_fly_wait + self.max_inter_fly_wait
                    if self.dispenser is not None:
                        self.dispenser.release_fly()

                #turn everything off if we have been waiting way too long
                if self.inter_fly_wait > self.turn_off_time:
                    self.shutdown()

        # can add ability to trigger UV light after a trial had gone long or fly hasn't moved

    def shutdown(self, app):
        app.exec_()

        # Shutdown timers
        if self.camera_timer is not None:
            self.camera_timer.stop()
        if self.cnc_timer is not None:
            self.cnc_timer.stop()
        if self.exp_data_timer is not None:
            self.exp_data_timer.stop()
        if self.dispenser_data_timer is not None:
            self.dispenser_data_timer.stop()
        if self.trial_timer is not None:
            self.trial_timer.stop()
        if self.light_checker_timer is not None:
            self.light_checker_timer.stop()
        if self.opto_timer is not None:
            self.otpo_timer.stop()

        # Shutdown extra views
        if self.dispenser_view is not None:
            self.dispenser_view.close()

        # Shutdown services
        if self.opto is not None:
            self.opto.off()
            self.opto.stop()
        if self.cam_view is not None:
            self.cam_view.close()
        if self.cam is not None:
            self.cam.stop()
        if self.tracker is not None:
            self.tracker.stop()
        if self.trial is not None:
            self.trial._stop_trial()
            self.trial.stop()
        if self.dispenser is not None:
            self.dispenser.stop()
        print('Shutdown Called')

    def closed_loop_pos_checked(self):
        if self.stim is not None:
            if self.ui.closed_loop_pos.isChecked():
                print('Enabling closed loop position...')
                self.stim.closed_loop_pos = True
            else:
                print('Disabling closed loop position...')
                self.stim.closed_loop_pos = False

    def closed_loop_angle_checked(self):
        if self.stim is not None:
            if self.ui.closed_loop_angle.isChecked():
                print('Enabling closed loop angle...')
                self.stim.closed_loop_angle = True
            else:
                print('Disabling closed loop angle...')
                self.stim.closed_loop_angle = False

class Mail():
    def __init__(self):
        message = None

class CncPopup(QMessageBox):
    def __init__(self, mail):
        super().__init__()
        self.title = 'box thing'
        self.left = 10
        self.top = 10
        self.width = 320
        self.height = 200
        self.initUI(mail)
    def initUI(self, mail):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        buttonReply = QMessageBox.question(self, 'CNC Control', "Would you like to initialize the CNC?",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if buttonReply == QMessageBox.Yes:
            mail.message = True
        else:
            mail.message = False
        self.show()

class MessagePopup(QMessageBox):
    def __init__(self, message):
        super().__init__()
        self.title = 'box thing'
        self.left = 600
        self.top = 400
        self.width = 320
        self.height = 200
        self.initUI(message)
    def initUI(self, message):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        QMessageBox.warning(self, 'Warning', '\n\n'.join(message))
        self.show()

# ref: https://github.com/bsdnoobz/opencv-code/blob/master/opencv-qt-integration-1/python/ImageViewer.py
class CameraView(QWidget):
    def __init__(self, cam, fps=24):
        super().__init__()
        self.title = 'Camera View'
        self.left = 794
        self.top = 23
        self.width = 659
        self.height = 496

        self.cam = cam

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_window)
        self.timer.start(int(1/fps*1000))

        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.image_label = QtWidgets.QLabel()
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addWidget(self.image_label)
        self.setLayout(self.main_layout)

        self.show()

    def update_window(self):
        try:
            img = self.cam.outFrame
        except:
            return

        if img is not None:
            height, width, bytesPerComponent = img.shape
            bytesPerLine = 3 * width
            cv2.cvtColor(img, cv2.COLOR_BGR2RGB, img)
            q_img = QtGui.QImage(img.data, width, height, bytesPerLine, QtGui.QImage.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(q_img)
            self.image_label.setPixmap(pixmap)

    def close(self):
        self.timer.stop()
        super().close()

class DispenserView(QWidget):
    def __init__(self, dispenser, fps=24):
        super().__init__()
        self.title = 'Dispenser View'
        self.left = 794
        self.top = 562
        self.width = 300
        self.height = 300

        self.dispenser = dispenser
        self.plot_data = np.zeros((128, 128))

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_window)
        self.timer.start(int(1/fps*1000))

        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.image_label = QtWidgets.QLabel()
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addWidget(self.image_label)
        self.setLayout(self.main_layout)

        self.show()

    def update_window(self):
        if self.dispenser.display_frame is not None:
            self.plot_data = np.roll(self.plot_data, 1, 0)
            self.plot_data[0] = self.dispenser.display_frame
            self.plot_data = self.plot_data.astype(np.uint8)
        img = QtGui.QImage(self.plot_data, self.plot_data.shape[0], self.plot_data.shape[1], QtGui.QImage.Format_Indexed8)
        pixmap = QtGui.QPixmap.fromImage(img)
        pixmap = pixmap.scaledToWidth(300)
        self.image_label.setPixmap(pixmap)

    def close(self):
        self.timer.stop()
        super().close()

class FlyPositionWindow(QWidget):
    def __init__(self, cam, cnc):
        super().__init__()
        self.cam=cam
        self.cnc=cnc
        self.title = 'Fly Position'
        self.left = 10
        self.top = 10
        self.width = 600
        self.height = 600
        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
 
        m = FlyPositionPlot(self, width=6, height=6, cam=self.cam, cnc=self.cnc)
        m.move(0,0)
 
        self.show()

class FlyPositionPlot(FigureCanvas):
    def __init__ (self, parent=None, width=6, height=6, dpi=100, cam=None,cnc=None):

        self.camThread = cam
        self.cncThread = cnc

        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        FigureCanvas.__init__(self, fig)
        self.setParent(parent)
        FigureCanvas.updateGeometry(self)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_ylim([0,80])
        self.ax.set_xlim([0,80])

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)

        # 100 ms was too fast...
        self.timer.start(1000)

    def update_plot(self):
        print('updating fly position plot {}'.format(time()))
        self.flyX = None
        self.flyY = None
        #camX = None
        #camY = None
        #cncX = None
        #cncY = None

        if self.camThread is not None and self.camThread.flyData is not None:
            camX = self.camThread.flyData.flyX
            camY = self.camThread.flyData.flyY
            flyPresent = self.camThread.flyData.flyPresent
        else:
            camX = None
            camY = None
            flyPresent = False

        if self.cncThread is not None and self.cncThread.cncThread is not None and self.cncThread.cncThread.status is not None:
            cncX = self.cncThread.cncThread.status.posX
            cncY = self.cncThread.cncThread.status.posY
        else:
            cncX = None
            cncY = None

        if camX is not None and cncX is not None:
            self.flyX = camX + cncX
            self.flyY = camY + cncY
        else:
            self.flyX = None
            self.flyY = None

        if self.flyY is not None and self.flyX is not None and flyPresent is True:
            self.ax.scatter(self.flyX*100, self.flyY*100, c='k', marker='o', s=2)
            self.draw()

def main():
    app = QApplication(sys.argv)
    dialog = QtWidgets.QMainWindow()
    prog = MainGui(dialog)
    #sys.exit(app.exec_())
    sys.exit(prog.shutdown(app))

if __name__ == '__main__':
    main()