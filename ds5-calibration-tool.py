#!/usr/bin/env python3

import usb.core
import usb.util
import array
import struct
import sys
import binascii
import time
from construct import *
import argparse

dev = None

VALID_DEVICE_IDS = [
    (0x054c, 0x0ce6)
]

def wait_for_device():
    global dev

    print("等待检测到 DualSense 手柄...")
    while True:
        for i in VALID_DEVICE_IDS:
            dev = usb.core.find(idVendor=i[0], idProduct=i[1])
            if dev is not None:
                print("检测到 DualSense 手柄: 供应商ID=%04x 产品ID=%04x" % (i[0], i[1]))
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
    assert isinstance(buf, (bytes, array.array)
                      ), 'set_report 的 buf 必须是缓冲区'
    assert report_id <= 0xff, '仅支持 report_type == 0'
    buf = struct.pack('B', report_id) + buf
    return dev.ctrl_transfer(HID_REQ.HOST_TO_DEV, HID_REQ.SET_REPORT, (3 << 8) | report_id, 0, buf)

def do_stick_center_calibration():
    print("开始进行摇杆中心校准...")

    deviceId = 1
    targetId = 1

    hid_set_report(dev, 0x82, struct.pack('BBB', 1, deviceId, targetId))

    k = hid_get_report(dev, 0x83, 4)
    if k != bytes([deviceId,targetId,1,0xff]):
        print("错误: DualSense 处于无效状态: %s. 请尝试重置" % (binascii.hexlify(k)))
        return

    while True:
        print("按 S 键采样数据或按 W 键保存校准数据（后跟回车）")
        X = input("> ").upper()
        if X == "S":
            hid_set_report(dev, 0x82, struct.pack('BBB', 3, deviceId, targetId))
            assert hid_get_report(dev, 0x83, 4) == bytes([deviceId,targetId,1,0xff])
        elif X == "W":
            hid_set_report(dev, 0x82, struct.pack('BBB', 2, deviceId, targetId))
            break
        else:
            print("无效命令")

    print("摇杆校准完成!!")

def do_stick_minmax_calibration():
    print("开始进行模拟摇杆最小最大值校准...")

    deviceId = 1
    targetId = 2

    hid_set_report(dev, 0x82, struct.pack('BBB', 1, deviceId, targetId))
    k = hid_get_report(dev, 0x83, 4)
    if k != bytes([deviceId,targetId,1,0xff]):
        print("错误: DualSense 处于无效状态: %s. 请尝试重置" % (binascii.hexlify(k)))
        return

    print("DualSense 现在正在采样数据。 将摇杆在其范围内移动")
    print("完成后，按任意键保存校准数据.")

    input()

    hid_set_report(dev, 0x82, struct.pack('BBB', 2, deviceId, targetId))

    print("摇杆校准完成!!")

if __name__ == "__main__":
    print("*********************************************************")
    print("* 欢迎使用 DualSense 手柄校准工具                     *")
    print("*                                                       *")
    print("* 此工具可能会损坏您的手柄。                            *")
    print("* 请自行承担风险。祝好运！ <3                           *")
    print("*                                                       *")
    print("* 版本 0.01 (C) 2024                      ~ by the_al ~ *")
    print("*********************************************************")

    parser = argparse.ArgumentParser(prog='ds5-calibration-tool')

    parser.add_argument('-p', '--permanent', help="使更改永久生效", action='store_true')
    subparsers = parser.add_subparsers(dest="action")

    p = subparsers.add_parser('analog-center', help="校准模拟摇杆中心")
    p.set_defaults(func=do_stick_center_calibration)

    p = subparsers.add_parser('analog-range', help="校准模拟摇杆范围")
    p.set_defaults(func=do_stick_minmax_calibration)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        exit(1)

    wait_for_device()

    # 分离内核驱动程序
    if sys.platform != 'win32' and dev.is_kernel_driver_active(0):
        try:
            dev.detach_kernel_driver(0)
        except usb.core.USBError as e:
            sys.exit('无法分离内核驱动程序: %s' % str(e))

    if dev == None:
        print("找不到 DualSense 手柄")
        exit(-1)

    print("== DualSense 已连接! ==")

    if args.permanent:
        print("正在解锁 NVS")
        hid_set_report(dev, 0x80, struct.pack('BBBBBB', 3, 2, 101, 50, 64, 12))

    try:
        args.func()
    except Exception as e:
        print(e)

    if args.permanent:
        print("正在重新锁定 NVS")
        hid_set_report(dev, 0x80, struct.pack('BB', 3, 1))
