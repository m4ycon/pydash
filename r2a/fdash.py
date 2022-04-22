# -*- coding: utf-8 -*-
"""
@author: Marcos F. Caetano (mfcaetano@unb.br) 03/11/2020

@description: PyDash Project

An implementation example of a FIXED R2A Algorithm.

the quality list is obtained with the parameter of handle_xml_response() method and the choice
is made inside of handle_segment_size_request(), before sending the message down.

In this algorithm the quality choice is always the same.
"""
import time
import math

from player.parser import *
from r2a.ir2a import IR2A
from base.whiteboard import Whiteboard


class FDash(IR2A):

  def __init__(self, id):
    IR2A.__init__(self, id)
    self.parsed_mpd = ''
    self.throughputs = []
    self.qi = []

    self.request_time = 0
    self.request_times = []
    self.buffer_sizes = []
    self.prev_bitrate = 46980

    self.whiteboard = Whiteboard.get_instance()

  def handle_xml_request(self, msg):
    self.request_time = time.perf_counter()
    self.send_down(msg)

  def handle_xml_response(self, msg):
    # getting qi list
    self.parsed_mpd = parse_mpd(msg.get_payload())
    self.qi = self.parsed_mpd.get_qi()
    self.send_up(msg)

    actual_time = time.perf_counter()
    t = actual_time - self.request_time
    self.throughputs.append(msg.get_bit_length() / t)

  def get_buffer_size(self):
    bs = self.whiteboard.get_playback_buffer_size()
    return bs[-1][-1] if len(bs) else 0

  def get_buffering_ling_vars(self, T):
    buffers = self.buffer_sizes[-1]

    # short, close, long
    S, C, L = 0, 0, 0
    if buffers < 2 * T / 3:
      S = 1
    elif buffers > T:
      S = 0
    else:
      S = -3 / T * buffers + 3

    if buffers < 2 * T / 3 or buffers > 4 * T:
      C = 0
    elif buffers < T:
      C = 3 / T * buffers - 2
    else:
      C = - buffers / (3 * T) + 4 / 3

    if buffers > 4 * T:
      L = 1
    elif buffers < T:
      L = 0
    else:
      L = buffers / (3 * T) - 1 / 3

    return S, C, L

  def get_diff_buffering_ling_vars(self, T):
    if len(self.buffer_sizes) < 2:
      return 0, 1, 0

    buffers_diff = self.buffer_sizes[-1] - self.buffer_sizes[-2]

    # falling, steady, rising
    F, S, R = 0, 0, 0
    if buffers_diff < - 2 / 3 * T:
      F = 1
    elif buffers_diff > 0:
      F = 0
    else:
      F = - 3 / (2 * T) * buffers_diff

    if buffers_diff < - 2 / 3 * T or buffers_diff > 4 * T:
      S = 0
    elif buffers_diff < 0:
      S = - 3 / (2 * T) * buffers_diff
    else:
      S = - buffers_diff / (4 * T) + 1

    if buffers_diff < 0:
      R = 0
    elif buffers_diff > 4 * T:
      R = 1
    else:
      R = buffers_diff / (4 * T)

    return F, S, R

  def get_rd(self, d):
    now = time.perf_counter()
    i_segment = 0
    for i, t in enumerate(self.request_times):
      if t > now - d:
        i_segment = i
        break

    rs = self.throughputs[i_segment:]
    len_throughputs = len(self.throughputs)
    rd = sum(rs) / (len_throughputs - i_segment)

    return rd

  def handle_segment_size_request(self, msg):
    # time to define the segment quality choose to make the request

    actual_time = time.perf_counter()
    dt = actual_time - self.request_time
    self.request_time = actual_time
    self.request_times.append(actual_time)
    self.buffer_sizes.append(self.get_buffer_size())

    # constants
    T = 30  # seconds
    d = 15  # seconds
    N2, N1, Z, P1, P2 = .25, .5, 1, 1.5, 2

    # linguistic variables
    short, close, long = self.get_buffering_ling_vars(T)
    falling, steady, rising = self.get_diff_buffering_ling_vars(T)

    # fuzzy if-then rules
    r1 = min(short, falling)
    r2 = min(close, falling)
    r3 = min(long, falling)
    r4 = min(short, steady)
    r5 = min(close, steady)
    r6 = min(long, steady)
    r7 = min(short, rising)
    r8 = min(close, rising)
    r9 = min(long, rising)

    I = math.sqrt(r9**2)
    SI = math.sqrt(r6**2 + r8**2)
    NC = math.sqrt(r3**2 + r5**2 + r7**2)
    SR = math.sqrt(r2**2 + r4**2)
    R = math.sqrt(r1**2)

    f = (N2 * R + N1 * SR + Z * NC + P1 *
         SI + P2 * I) / (SR + R + NC + SI + I)

    rd = self.get_rd(d)
    bi_next = f * rd

    bn = self.qi[0]
    len_qi = len(self.qi)
    for i in range(len_qi):
      if self.qi[len_qi-i-1] < bi_next:
        bn = self.qi[len_qi-i-1]
        break

    bi = self.throughputs[-1]

    qi_selected = self.qi[0]
    if (bn > bi and short > 0) or (bn < bi and long > 0):
      qi_selected = self.prev_bitrate
    else:
      qi_selected = bn

    self.prev_bitrate = qi_selected
    msg.add_quality_id(qi_selected)
    self.send_down(msg)

  def handle_segment_size_response(self, msg):
    actual_time = time.perf_counter()
    t = actual_time - self.request_time
    self.throughputs.append(msg.get_bit_length() / t)

    self.send_up(msg)

  def initialize(self):
    pass

  def finalization(self):
    pass
