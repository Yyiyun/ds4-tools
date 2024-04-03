#!/usr/bin/env python3

import usb.core
import usb.util
import array
import struct
import sys
import binascii
import time
from construct import *

dev = None

VALID_DEVICE_IDS = [
    (0x054c, 0x05c4),
    (0x054c, 0x09cc)
]

def wait_for_device():
    global dev

    print("等待 DualShock 4 手柄连接...")
    while True:
        for i in VALID_DEVICE_IDS:
            dev = usb.core.find(idVendor=i[0], idProduct=i[1])
            if dev is not None:
                print("检测到 DualShock 4 手柄: 供应商ID=%04x 产品ID=%04x" % (i[0], i[1]))
                return
        time.sleep(1)

class HID_REQ:
    DEV_TO_HOST = usb.util.build_request_type(
        usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
    HOST_TO_DEV = usb.util.build_request_type(
        usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
    GET_REPORT = 0x01
    SET_REPORT = 0x09

def hid_get_report(dev, report_id, size):
    assert isinstance(size, int), 'get_report 的大小必须是整数'
    assert report_id <= 0xff, '仅支持 report_type == 0'
    return dev.ctrl_transfer(HID_REQ.DEV_TO_HOST, HID_REQ.GET_REPORT, report_id, 0, size + 1)[1:].tobytes()

def hid_set_report(dev, report_id, buf):
    assert isinstance(buf, (bytes, array.array)), 'set_report 的 buf 必须是缓冲区'
    assert report_id <= 0xff, '仅支持 report_type == 0'
    buf = struct.pack('B', report_id) + buf
    return dev.ctrl_transfer(HID_REQ.HOST_TO_DEV, HID_REQ.SET_REPORT, (3 << 8) | report_id, 0, buf)

def dump_93_data():
    data = hid_get_report(dev, 0x93, 13)
    assert len(data) == 13
    deviceId, targetId, numChunks, curChunk, dataLen = struct.unpack('BBBBBxxxxxxxx', data)
    if deviceId == 0xff and targetId == 0xff:
        print("没有数据可读")
        return []

    theDeviceId, theTargetId = deviceId, targetId

    print("数据分成 %d 个块; 我们在第 %d 块" % (numChunks, curChunk))
    if numChunks == 0:
        return []

    assert dataLen >= 0 and dataLen <= 8
    out = [data[5:5+dataLen]]

    while curChunk < numChunks - 1:
        data = hid_get_report(dev, 0x93, 13)
        assert len(data) == 13
        deviceId, targetId, numChunks, curChunk, dataLen = struct.unpack('BBBBBxxxxxxxx', data)
        if deviceId == 0xff or targetId == 0xff:
            print("没有更多数据")
            return out

        assert (deviceId, targetId) == (theDeviceId, theTargetId)
        out += [data[5:5+dataLen]]
    return out

def do_trigger_calibration():
    print("开始进行扳机校准...")

    deviceId = 3

    hid_set_report(dev, 0x90, struct.pack('BBBB', 1, deviceId, 0, 3))

    for i in range(2):
        print("L2: 松开并按回车")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 1, 1))

    for i in range(2):
        print("L2: 中间并按回车")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 2, 1))

    for i in range(2):
        print("L2: 完全按下并按回车")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 3, 1))

    for i in range(2):
        print("R2: 松开并按回车")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 1, 2))

    for i in range(2):
        print("R2: 中间并按回车")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 2, 2))

    for i in range(2):
        print("R2: 完全按下并按回车")
        input()
        hid_set_report(dev, 0x90, struct.pack('BBBB', 3, deviceId, 3, 2))

    print("写入.")
    hid_set_report(dev, 0x90, struct.pack('BBBB', 2, deviceId, 0, 3))

    print("扳机校准完成!!")
    print()

    print("这是来自 DS4 的一些关于校准的调试数据")
    data = dump_93_data()
    for i in range(len(data)):
        print("样本 %d, 数据=%s" % (i, binascii.hexlify(data[i]).decode('utf-8')))

def do_stick_center_calibration():
    print("开始进行摇杆中心校准...")

    deviceId = 1
    targetId = 1

    hid_set_report(dev, 0x90, struct.pack('BBB', 1, deviceId, targetId))
    while True:
        assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,1])
        assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,0xff])
        print("按 S 键采样数据或按 W 键保存校准数据（后跟回车）")
        X = input("> ").upper()
        if X == "S":
            hid_set_report(dev, 0x90, struct.pack('BBB', 3, deviceId, targetId))
        elif X == "W":
            hid_set_report(dev, 0x90, struct.pack('BBB', 2, deviceId, targetId))
            break
        else:
            print("无效命令")

    assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,2])
    assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,1])

    print("摇杆校准完成!!")
    print()

    print("这是来自 DS4 的一些关于校准的调试数据")
    data = dump_93_data()
    for i in range(len(data)):
        print("样本 %d, 数据=%s" % (i, binascii.hexlify(data[i]).decode('utf-8')))

def do_stick_minmax_calibration():
    print("开始进行模拟摇杆最小最大值校准...")

    deviceId = 1
    targetId = 2

    hid_set_report(dev, 0x90, struct.pack('BBB', 1, deviceId, targetId))
    assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,1])
    assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,0xff])

    print("DualShock 4 现在正在采样数据。 将模拟摇杆在其范围内移动")
    print("完成后，按任意键保存校准数据.")

    input()

    hid_set_report(dev, 0x90, struct.pack('BBB', 2, deviceId, targetId))

    assert hid_get_report(dev, 0x91, 3) == bytes([deviceId,targetId,2])
    assert hid_get_report(dev, 0x92, 3) == bytes([deviceId,targetId,1])

    print("摇杆校准完成!!")
    print()

    print("这是来自 DS4 的一些关于校准的调试数据")
    data = dump_93_data()
    for i in range(len(data)):
        print("样本 %d, 数据=%s" % (i, binascii.hexlify(data[i]).decode('utf-8')))

def menu():
    print("")
    print("请选择要校准的项目:")
    print("1. 摇杆中心")
    print("2. 摇杆范围（最小-最大）")
    print("3. L2 / R2（测试版，如果可用，请告知）")

    choice_int = -1
    try:
        choice_int = int(input("> "))
    except:
        print("无效的选择.")
        return

    if choice_int == 1:
        do_stick_center_calibration()
    if choice_int == 2:
        do_stick_minmax_calibration()
    if choice_int == 3:
        do_trigger_calibration()

if __name__ == "__main__":
    print("*********************************************************")
    print("* 欢迎使用 DualShock 4 手柄校准工具                   *")
    print("*                                                       *")
    print("* 此工具可能会损坏您的手柄。                            *")
    print("* 请自行承担风险。祝好运！ <3                           *")
    print("*                                                       *")
    print("* 版本 0.01                               ~ by the_al ~ *")
    print("*********************************************************")

    wait_for_device()

    # 分离内核驱动程序
    if sys.platform != 'win32' and dev.is_kernel_driver_active(0):
        try:
            dev.detach_kernel_driver(0)
        except usb.core.USBError as e:
            sys.exit('无法分离内核驱动程序: %s' % str(e))

    if dev != None:
        print("DualShock 4 已连接!")
        menu()
