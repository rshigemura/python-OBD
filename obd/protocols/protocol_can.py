
########################################################################
#                                                                      #
# python-OBD: A python OBD-II serial module derived from pyobd         #
#                                                                      #
# Copyright 2004 Donour Sizemore (donour@uchicago.edu)                 #
# Copyright 2009 Secons Ltd. (www.obdtester.com)                       #
# Copyright 2009 Peter J. Creath                                       #
# Copyright 2015 Brendan Whitfield (bcw7044@rit.edu)                   #
#                                                                      #
########################################################################
#                                                                      #
# protocols/protocol_can.py                                            #
#                                                                      #
# This file is part of python-OBD (a derivative of pyOBD)              #
#                                                                      #
# python-OBD is free software: you can redistribute it and/or modify   #
# it under the terms of the GNU General Public License as published by #
# the Free Software Foundation, either version 2 of the License, or    #
# (at your option) any later version.                                  #
#                                                                      #
# python-OBD is distributed in the hope that it will be useful,        #
# but WITHOUT ANY WARRANTY; without even the implied warranty of       #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the        #
# GNU General Public License for more details.                         #
#                                                                      #
# You should have received a copy of the GNU General Public License    #
# along with python-OBD.  If not, see <http://www.gnu.org/licenses/>.  #
#                                                                      #
########################################################################

from obd.utils import contiguous
from .protocol import *


class CANProtocol(Protocol):

    TX_ID_ENGINE = 0

    FRAME_TYPE_SF = 0x00  # single frame
    FRAME_TYPE_FF = 0x10  # first frame of multi-frame message
    FRAME_TYPE_CF = 0x20  # consecutive frame(s) of multi-frame message


    def __init__(self, lines_0100, id_bits):
        # this needs to be set FIRST, since the base
        # Protocol __init__ uses the parsing system.
        self.id_bits = id_bits
        Protocol.__init__(self, lines_0100)


    def parse_frame(self, frame):

        raw = frame.raw

        # pad 11-bit CAN headers out to 32 bits for consistency,
        # since ELM already does this for 29-bit CAN headers

        #        7 E8 06 41 00 BE 7F B8 13
        # to:
        # 00 00 07 E8 06 41 00 BE 7F B8 13

        if self.id_bits == 11:
            raw = "00000" + raw

        raw_bytes = ascii_to_bytes(raw)

        # read header information
        if self.id_bits == 11:
            # Ex.
            #       [   ]
            # 00 00 07 E8 06 41 00 BE 7F B8 13

            frame.priority = raw_bytes[2] & 0x0F  # always 7
            frame.addr_mode = raw_bytes[3] & 0xF0  # 0xD0 = functional, 0xE0 = physical

            if frame.addr_mode == 0xD0:
                #untested("11-bit functional request from tester")
                frame.rx_id = raw_bytes[3] & 0x0F  # usually (always?) 0x0F for broadcast
                frame.tx_id = 0xF1  # made-up to mimic all other protocols
            elif raw_bytes[3] & 0x08:
                frame.rx_id = 0xF1  # made-up to mimic all other protocols
                frame.tx_id = raw_bytes[3] & 0x07
            else:
                #untested("11-bit message header from tester (functional or physical)")
                frame.tx_id = 0xF1  # made-up to mimic all other protocols
                frame.rx_id = raw_bytes[3] & 0x07

        else: # self.id_bits == 29:
            frame.priority  = raw_bytes[0]  # usually (always?) 0x18
            frame.addr_mode = raw_bytes[1]  # DB = functional, DA = physical
            frame.rx_id     = raw_bytes[2]  # 0x33 = broadcast (functional)
            frame.tx_id     = raw_bytes[3]  # 0xF1 = tester ID

        # extract the frame data
        #             [      Frame       ]
        # 00 00 07 E8 06 41 00 BE 7F B8 13
        frame.data = raw_bytes[4:]


        # read PCI byte (always first byte in the data section)
        #             v
        # 00 00 07 E8 06 41 00 BE 7F B8 13
        frame.type = frame.data[0] & 0xF0
        if frame.type not in [self.FRAME_TYPE_SF,
                              self.FRAME_TYPE_FF,
                              self.FRAME_TYPE_CF]:
            debug("Dropping frame carrying unknown PCI frame type")
            return False


        if frame.type == self.FRAME_TYPE_SF:
            # single frames have 4 bit length codes
            #              v
            # 00 00 07 E8 06 41 00 BE 7F B8 13
            frame.data_len = frame.data[0] & 0x0F
        elif frame.type == self.FRAME_TYPE_FF:
            # First frames have 12 bit length codes
            #              v
            # 00 00 07 E8 06 41 00 BE 7F B8 13
            frame.data_len = (frame.data[0] & 0x0F) << 8
            frame.data_len += frame.data[1]
        elif frame.type == self.FRAME_TYPE_CF:
            # Consecutive frames have 4 bit sequence indices
            frame.seq_index = frame.data[0] & 0x0F

        return True


    def parse_message(self, message):

        frames = message.frames

        if len(frames) == 1:
            frame = frames[0]

            if frame.type != self.FRAME_TYPE_SF:
                debug("Recieved lone frame not marked as single frame")
                return False

            # extract data, ignore PCI byte and anything after the marked length
            #             [      Frame       ]
            #                [     Data      ]
            # 00 00 07 E8 06 41 00 BE 7F B8 13 xx xx xx xx, anything else is ignored
            message.data = frame.data[1:1+frame.data_len]

        else:
            # sort FF and CF into their own lists

            ff = []
            cf = []

            for f in frames:
                if f.type == self.FRAME_TYPE_FF:
                    ff.append(f)
                elif f.type == self.FRAME_TYPE_CF:
                    cf.append(f)
                else:
                    debug("Dropping frame in multi-frame response not marked as FF or CF")

            # check that we captured only one first-frame
            if len(ff) > 1:
                debug("Recieved multiple frames marked FF")
                return False
            elif len(ff) == 0:
                debug("Never received frame marked FF")
                return False

            # check that there was at least one consecutive-frame
            if len(cf) == 0:
                debug("Never received frame marked CF")
                return False

            # calculate proper sequence indices from the lower 4 bits given
            for prev, curr in zip(cf, cf[1:]):
                # Frame sequence numbers only specify the low order bits, so compute the
                # full sequence number from the frame number and the last sequence number seen:
                # 1) take the high order bits from the last_sn and low order bits from the frame
                seq = (prev.seq_index & ~0x0F) + (curr.seq_index)
                # 2) if this is more than 7 frames away, we probably just wrapped (e.g.,
                # last=0x0F current=0x01 should mean 0x11, not 0x01)
                if seq < prev.seq_index - 7:
                    # untested
                    seq += 0x10

                curr.seq_index = seq

            # sort the sequence indices
            cf = sorted(cf, key=lambda f: f.seq_index)

            # check contiguity, and that we aren't missing any frames
            indices = [f.seq_index for f in cf]
            if not contiguous(indices, 1, len(cf)):
                debug("Recieved multiline response with missing frames")
                return False


            # first frame:
            #             [       Frame         ]
            #             [PCI]                   <-- first frame has a 2 byte PCI
            #              [L ] [     Data      ] L = length of message in bytes
            # 00 00 07 E8 10 13 49 04 01 35 36 30


            # consecutive frame:
            #             [       Frame         ]
            #             []                       <-- consecutive frames have a 1 byte PCI
            #              N [       Data       ]  N = current frame number (rolls over to 0 after F)
            # 00 00 07 E8 21 32 38 39 34 39 41 43
            # 00 00 07 E8 22 00 00 00 00 00 00 31


            # original data:
            # [     specified message length (from first-frame)      ]
            # 49 04 01 35 36 30 32 38 39 34 39 41 43 00 00 00 00 00 00 31


            # on the first frame, skip PCI byte AND length code
            message.data = ff[0].data[2:]

            # now that they're in order, load/accumulate the data from each CF frame
            for f in cf:
                message.data += f.data[1:] # chop off the PCI byte

            # chop to the correct size (as specified in the first frame)
            message.data = message.data[:ff[0].data_len]


        # chop off the Mode/PID bytes based on the mode number
        mode = message.data[0]
        if mode == 0x43:

            # TODO: confirm this logic. I don't have any raw test data for it yet

            # fetch the DTC count, and use it as a length code
            num_dtc_bytes = message.data[1] * 2

            # skip the PID byte and the DTC count,
            message.data = message.data[2:][:num_dtc_bytes]

        else:
            # skip the Mode and PID bytes
            #
            # single line response:
            #                      [  Data   ]
            # 00 00 07 E8 06 41 00 BE 7F B8 13
            #
            # OR, the data from a multiline response:
            #       [                     Data                       ]
            # 49 04 01 35 36 30 32 38 39 34 39 41 43 00 00 00 00 00 00
            message.data = message.data[2:]

        return True


##############################################
#                                            #
# Here lie the class stubs for each protocol #
#                                            #
##############################################



class ISO_15765_4_11bit_500k(CANProtocol):
    ELM_NAME = "ISO 15765-4 (CAN 11/500)"
    ELM_ID = "6"
    def __init__(self, lines_0100):
        CANProtocol.__init__(self, lines_0100, id_bits=11)


class ISO_15765_4_29bit_500k(CANProtocol):
    ELM_NAME = "ISO 15765-4 (CAN 29/500)"
    ELM_ID = "7"
    def __init__(self, lines_0100):
        CANProtocol.__init__(self, lines_0100, id_bits=29)


class ISO_15765_4_11bit_250k(CANProtocol):
    ELM_NAME = "ISO 15765-4 (CAN 11/250)"
    ELM_ID = "8"
    def __init__(self, lines_0100):
        CANProtocol.__init__(self, lines_0100, id_bits=11)


class ISO_15765_4_29bit_250k(CANProtocol):
    ELM_NAME = "ISO 15765-4 (CAN 29/250)"
    ELM_ID = "9"
    def __init__(self, lines_0100):
        CANProtocol.__init__(self, lines_0100, id_bits=29)


class SAE_J1939(CANProtocol):
    ELM_NAME = "SAE J1939 (CAN 29/250)"
    ELM_ID = "A"
    def __init__(self, lines_0100):
        CANProtocol.__init__(self, lines_0100, id_bits=29)
