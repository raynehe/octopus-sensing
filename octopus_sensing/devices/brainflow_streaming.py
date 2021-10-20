# This file is part of Octopus Sensing <https://octopus-sensing.nastaran-saffar.me/>
# Copyright © Nastaran Saffaryazdi 2020
#
# Octopus Sensing is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
#  either version 3 of the License, or (at your option) any later version.
#
# Octopus Sensing is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with Octopus Sensing.
# If not, see <https://www.gnu.org/licenses/>.

import os
import threading
import csv
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams

from octopus_sensing.common.message_creators import MessageType
from octopus_sensing.devices.monitored_device import MonitoredDevice
from octopus_sensing.devices.common import SavingModeEnum


class BrainFlowStreaming(MonitoredDevice):
    '''
    Manage brainflow streaming

    Attributes
    -----------
    device_id: str
        Device ID. 
        Brainflow support a list of devices, to see supported device IDs go to:
        https://brainflow.readthedocs.io/en/stable/SupportedBoards.html
    
    sampling_rate: int
        the sampling rate for recording data
    
    brain_flow_input_params: BrainFlowInputParams
        Each supported board in brainflow gets some parameters, to see the list
        of parameters for each board go to:
        https://brainflow.readthedocs.io/en/stable/SupportedBoards.html

    saving_mode: int, optional, default = SavingModeEnum.CONTINIOUS_SAVING_MODE
        The way of saving data. I saves data continiously in a file 
        or saves data which are related to various stimulus in separate files. 
        SavingModeEnum: CONTINIOUS_SAVING_MODE
                        SEPARATED_SAVING_MODE

    **kwargs : dict, optional
            Extra optional arguments
    
    See Also
    -----------
    DeviceCoordinator
        DeviceCoordinator is managing data recording by sending messages to this class 
        
    '''
    def __init__(self,
                 device_id: str,
                 sampling_rate: int,
                 brain_flow_input_params: BrainFlowInputParams,
                 saving_mode: int=SavingModeEnum.CONTINIOUS_SAVING_MODE,
                 **kwargs):
        super().__init__(**kwargs)

        self._saving_mode = saving_mode
        self._stream_data = []
        self.sampling_rate = sampling_rate

        self._board = BoardShim(device_id, brain_flow_input_params)
        self._board.set_log_level(0)
        self._board.prepare_session()
        self._terminate = False
        self._trigger = None
        self._experiment_id = None

        self.output_path = os.path.join(self.output_path, self.name)
        os.makedirs(self.output_path, exist_ok=True)

    def _run(self):
        threading.Thread(target=self._stream_loop).start()

        while True:
            message = self.message_queue.get()
            if message is None:
                continue
            if message.type == MessageType.START:
                self.__set_trigger(message)
                self._experiment_id = message.experiment_id
            elif message.type == MessageType.STOP:
                if self._saving_mode == SavingModeEnum.SEPARATED_SAVING_MODE:
                    self._experiment_id = message.experiment_id
                    file_name = \
                        "{0}/{1}-{2}-{3}.csv".format(self.output_path,
                                                     self.name,
                                                     self._experiment_id,
                                                     message.stimulus_id)
                    self._save_to_file(file_name)
                    self._stream_data = []
                else:
                    self._experiment_id = message.experiment_id
                    self.__set_trigger(message)
            elif message.type == MessageType.TERMINATE:
                self._terminate = True
                if self._saving_mode == SavingModeEnum.CONTINIOUS_SAVING_MODE:
                    file_name = \
                        "{0}/{1}-{2}.csv".format(self.output_path,
                                                 self.name,
                                                 self._experiment_id)
                    self._save_to_file(file_name)
                break

        self._board.stop_stream()

    def _stream_loop(self):
        self._board.start_stream()
        while True:
            if self._terminate is True:
                break
            data = self._board.get_board_data()
            if np.array(data).shape[1] is not 0:
                self._stream_data.extend(list(np.transpose(data)))
                if self._trigger is not None:
                    last_record = self._stream_data.pop()
                    print("type", type(last_record))
                    print(list(last_record))
                    last_record = list(last_record)
                    last_record.append(self._trigger)
                    print(last_record)
                    print(len(last_record))
                    self._stream_data.append(last_record)
                self._trigger = None

    def __set_trigger(self, message):
        '''
        Takes a message and set the trigger using its data
        
        Parameters
        ----------
        message: Message
            a message object
        '''
        self._trigger = \
            "{0}-{1}-{2}".format(message.type,
                                 message.experiment_id,
                                 str(message.stimulus_id).zfill(2))
        print(self._trigger)

    def _save_to_file(self, file_name):
        if not os.path.exists(file_name):
            csv_file = open(file_name, 'a')
            writer = csv.writer(csv_file)
            if self.header is not None:
                writer.writerow(self.header)
                csv_file.flush()
                csv_file.close()
        with open(file_name, 'a') as csv_file:
            writer = csv.writer(csv_file)
            print(len(self._stream_data))
            for row in self._stream_data:
                writer.writerow(row)
                csv_file.flush()

    def _get_monitoring_data(self):
        '''Returns latest collected data for monitoring/visualizing purposes.'''
        # Last three seconds
        # FIXME: hard-coded data collection rate
        return self._stream_data[-1 * 3 * self.sampling_rate:]
