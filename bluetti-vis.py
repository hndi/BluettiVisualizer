#Bluetti Visualizer by hndi, MIT license
#Based on the bluetti logger from bluetti-mqqt by Stephen Augenstein, MIT License
#
#Used libraries: bluetti_mqqt, pyqt5, plyer, vlc
#
#To scan your device address, type: python3 bluetti-vis.py --scan
#To start the visualizer, type: python3 bluetti.py --log <logfile> <device address>


import sys
import threading

from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsLineItem
from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtGui import QIcon
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QFont
import PyQt5
from PyQt5.QtCore import QTimer, QSize, Qt


import math
from plyer import notification

import argparse
import asyncio
import base64
from bleak import BleakError
from io import TextIOWrapper
import json
import sys
import textwrap
import time
from datetime import datetime
from typing import cast
from bluetti_mqtt.bluetooth import (
    check_addresses, scan_devices, BluetoothClient, ModbusError,
    ParseError, BadConnectionError
)
from bluetti_mqtt.core import (
    BluettiDevice, ReadHoldingRegisters, DeviceCommand
)

import vlc


class BluettiData():

    wattHInDCSum = 0.0
    wattHInACSum = 0.0
    wattHOutDCSum = 0.0
    wattHOutACSum = 0.0
    corrWattHSolar = 0.0
    batteryInOutWh = 0.0
    batteryPerc = 0.0
    dcInWatts = 0.0
    acInWatts = 00.0
    dcOutWatts = 00.0
    acOutWatts = 500.0
    dcOutOn = False
    acOutOn = False
    batInOutWatts = 0.0
    batInWh = 0.0
    batOutWh = 0.0
    connectTime = 0.0
    runTime = 0.0
    batteryInOutWh = 0.0
    solarMaxW = 0.0
    solarWAvgSum = 0
    solarWAvgCnt = 0




bdata = BluettiData()
lastValsTime = 0.0
lastHistory = 0.0
lastLog = 0.0
exitFlag = False
guiProgVals = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
guiProgVis = [False, False, False, False, False, False]
solarInHistory = []
battPercHistory = []
battInOutHistory = []
DCOutHistory = []
ACOutHistory = []
newHourHistory = []
historyEntries = 0
connected = False
lastconnectionTime = 0.0

chargePercWarning = 80
dischargePercWarning = 20
lastPerc = -1
lastHour = -1

updateGUI = False



def log_invalid(output: TextIOWrapper, err: Exception, command: DeviceCommand):
    log_entry = {
        'type': 'client',
        'time': time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime()),
        'error': err.args[0],
        'command': base64.b64encode(bytes(command)).decode('ascii'),
    }
    #output.write(json.dumps(log_entry) + '\n')


def handleBluettiData(output: TextIOWrapper, data):
    global lastLog, lastHistory, lastValsTime, wattHInACSum, wattHInDCSum, wattHOutACSum, wattHOutDCSum, corrWattHSolar, batteryInOutWh
    global solarInHistory, DCOutHistory, ACOutHistory, battPercHistory, battInOutHistory, historyEntries, lastPerc, lastHour, updateGUI, connected, lastconnectionTime

    textOut = ""
    currTime = time.time()

    try:
        bdata.batteryPerc = data['total_battery_percent']
        bdata.dcInWatts = data['dc_input_power']
        bdata.acInWatts = data['ac_input_power']
        bdata.dcOutWatts = data['dc_output_power']
        bdata.acOutWatts = data['ac_output_power']
        bdata.dcOutOn = data['dc_output_on']
        bdata.acOutOn = data['ac_output_on']

    except Exception as e:
        #print(f"Error: {e}")
        pass

        #todo: wtf, weird indentation? need to fix this. why is it under except? somehow only works that way, lol

        if connected == True and lastconnectionTime > 0:
            bdata.connectTime += currTime - lastconnectionTime
        connected = True
        lastconnectionTime = currTime

        lastValTimePassed = currTime - lastValsTime
        if lastValsTime > 0.0 and lastValTimePassed > 0.0 and lastValTimePassed < 60.0:
            bdata.wattHInACSum += bdata.acInWatts * (lastValTimePassed / 3600.0);
            bdata.wattHInDCSum += bdata.dcInWatts * (lastValTimePassed / 3600.0);
            bdata.wattHOutACSum += bdata.acOutWatts * (lastValTimePassed / 3600.0);
            bdata.wattHOutDCSum += bdata.dcOutWatts * (lastValTimePassed / 3600.0);

            standByBlueToothIdlePowerW = 3.57
            solarConvEfficiency = 0.96
            ACConvEfficiency = 0.96 #todo
            dcOutputIdlePowerW = 1.1
            acOutputIdlePowerW = 7.5

            if bdata.dcInWatts > 0:
                bdata.solarWAvgSum += bdata.dcInWatts
                bdata.solarWAvgCnt += 1

            if bdata.dcInWatts > bdata.solarMaxW:
                bdata.solarMaxW = bdata.dcInWatts

            if bdata.dcInWatts >= 10.0:
                bdata.corrWattHSolar += (solarConvEfficiency * bdata.dcInWatts - 0.0) * (lastValTimePassed / 3600.0)
                bdata.corrWattHSolar -= standByBlueToothIdlePowerW * (lastValTimePassed / 3600.0)

            else:
                if bdata.dcInWatts > 0:
                    bdata.corrWattHSolar -= 0.0 * (lastValTimePassed / 3600.0)
                    bdata.corrWattHSolar -= max(standByBlueToothIdlePowerW - bdata.dcInWatts, 0.0) * (lastValTimePassed / 3600.0) # <-- nochmal checken, warum das mitm min nicht geklappt hat
                else:
                    bdata.corrWattHSolar -= standByBlueToothIdlePowerW * (lastValTimePassed / 3600.0)

            if bdata.dcOutOn == True:
                bdata.corrWattHSolar -= dcOutputIdlePowerW * (lastValTimePassed / 3600.0)

            if bdata.acOutOn == True:
                bdata.corrWattHSolar -= acOutputIdlePowerW * (lastValTimePassed / 3600.0)


            lastVal = bdata.batteryInOutWh
            bdata.batteryInOutWh = bdata.corrWattHSolar + (bdata.wattHInACSum * ACConvEfficiency) - bdata.wattHOutACSum - bdata.wattHOutDCSum
            bdata.batInOutWatts = (bdata.batteryInOutWh - lastVal) / (lastValTimePassed / 3600)
            if bdata.batteryInOutWh > lastVal:
                bdata.batInWh -= (lastVal - bdata.batteryInOutWh)
            else:
                bdata.batOutWh += (lastVal - bdata.batteryInOutWh)

        #indentation end


        if lastPerc != bdata.batteryPerc and lastPerc > -1:
            if bdata.batteryPerc > lastPerc:
                if lastPerc < chargePercWarning and bdata.batteryPerc >= chargePercWarning:
                    notification.notify(
                        title = "Battery charge warning ⚠",
                        message = "🔋 The battery is charged up to " + str(bdata.batteryPerc) + "%",
                        app_icon = "example.png",
                        timeout = 0,
                    )
                    mp.play()
            if bdata.batteryPerc < lastPerc:
                if lastPerc > dischargePercWarning and bdata.batteryPerc <= dischargePercWarning:
                    notification.notify(
                        title = "Battery discharge warning ⚠",
                        message = "🪫 The battery is discharged to " + str(bdata.batteryPerc) + "%",
                        app_icon = "example.png",
                        timeout = 0,
                    )
                    mp.play()

        lastPerc = bdata.batteryPerc

        lastValsTime = currTime;

        textOut =str(bdata.batteryPerc) + ";" + str(bdata.dcInWatts) + ";" + str(bdata.acInWatts) + ";" + str(bdata.dcOutWatts) + ";" + str(bdata.acOutWatts) + ";" + str(bdata.dcOutOn) + ";" + str(bdata.acOutOn) + ";" + str(round(bdata.wattHInDCSum, 3)) + ";" + str(round(bdata.wattHInACSum,2)) + ";" + str(round(bdata.wattHOutDCSum, 3)) + ";" + str(round(bdata.wattHOutACSum,3)) + ";" + str(round(bdata.corrWattHSolar,3)) + ";" + str(round(bdata.batInOutWatts, 3)) + ";" + str(round(bdata.batteryInOutWh, 3))
        print(textOut.replace(";", "\t"))

        updateGUI = True


    if (textOut != "" and (currTime - lastLog >= 10.0)):
        output.write(str(round(currTime)) + ";" + textOut + "\n")
        output.flush()
        lastLog = currTime


    if (currTime - lastHistory >= 10.0):
        lastHistory = currTime
        currHour = datetime.fromtimestamp(currTime).hour

        solarInHistory.append(bdata.dcInWatts)
        battPercHistory.append(bdata.batteryPerc)
        battInOutHistory.append(bdata.batInOutWatts)
        ACOutHistory.append(bdata.acOutWatts)
        DCOutHistory.append(bdata.dcOutWatts)
        if currHour != lastHour and lastHour != -1:
            newHourHistory.append(currHour)
        else:
            newHourHistory.append(-1)
        drawAllGraphs()
        historyEntries += 1
        lastHour = currHour

async def log_command(client: BluetoothClient, device: BluettiDevice, command: DeviceCommand, log_file: TextIOWrapper):
    response_future = await client.perform(command)
    try:
        response = cast(bytes, await response_future)
        if isinstance(command, ReadHoldingRegisters):
            body = command.parse_response(response)
            parsed = device.parse(command.starting_address, body)
            handleBluettiData(log_file, parsed)

    except (BadConnectionError, BleakError, ModbusError, ParseError) as err:
        print(f'Got an error running command {command}: {err}')
        log_invalid(log_file, err, command)


async def log(address: str, path: str):
    print("Checking connection to Bluetti...")
    devices = await check_addresses({address})
    if len(devices) == 0:
        print("Could not find the given device to connect to. If the bluetooth address is correct try disabling and re-enabling bluetooth (common bug).")

        sys.exit('Could not find the given device to connect to')

    device = devices[0]

    print(f'Connecting to {device.address}')
    client = BluetoothClient(device.address)
    asyncio.get_running_loop().create_task(client.run())

    with open(path, 'a') as log_file:
        # Wait for device connection
        while not client.is_ready:
            print('Waiting for connection...')
            await asyncio.sleep(1)
            continue

        # Poll device
        while exitFlag == False:
            for command in device.logging_commands:
                await log_command(client, device, command, log_file)

            # Skip pack polling if not available
            if len(device.pack_logging_commands) == 0:
                continue

            for pack in range(1, device.pack_num_max + 1):
                # Send pack set command if the device supports more than 1 pack
                if device.pack_num_max > 1:
                    command = device.build_setter_command('pack_num', pack)
                    await log_command(client, device, command, log_file)
                    await asyncio.sleep(10)  # We need to wait after switching packs for the data to be available

                for command in device.pack_logging_commands:
                    await log_command(client, device, command, log_file)



def initLogging():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Scans for Bluetti devices and logs information',
        epilog=textwrap.dedent("""\
            To use, run the scanner first:
            %(prog)s --scan

            Once you have found your device you can run the logger:
            %(prog)s --log log-file.log 00:11:22:33:44:55
            """))
    parser.add_argument(
        '--scan',
        action='store_true',
        help='Scans for devices and prints out addresses')
    parser.add_argument(
        '--log',
        metavar='PATH',
        help='Connect and log data for the device to the given file')
    parser.add_argument(
        'address',
        metavar='ADDRESS',
        nargs='?',
        help='The device MAC to connect to for logging')
    args = parser.parse_args()
    if args.scan:
        asyncio.run(scan_devices())
    elif args.log:
        asyncio.run(log(args.address, args.log))
    else:
        parser.print_help()

    pass

def initWindow(win):
    #Main Window
    win.setGeometry(100, 100, 1170, 800)
    win.setWindowTitle("Bluetti")
    win.setFixedSize(1170, 800)


    font = QFont()
    font.setPointSize(24)
    font.setBold(True)

    #Graphical Area
    pixmap = QPixmap('background.png')
    win.lblGfxBG = QtWidgets.QLabel(win)
    win.lblGfxBG.setGeometry(0, 0, 500, 800)
    win.lblGfxBG.setPixmap(pixmap)
    win.lblGfxBG.show()

    win.lblDCin = QtWidgets.QLabel(win)
    win.lblDCin.setText("0W")
    win.lblDCin.move(108, 50)
    win.lblDCin.setFont(font)
    win.lblDCin.setStyleSheet("color: #EEEEEE")
    win.lblDCin.show()


    win.lblACin = QtWidgets.QLabel(win)
    win.lblACin.setText("0W")
    win.lblACin.move(108, 600)
    win.lblACin.setFont(font)
    win.lblACin.setStyleSheet("color: #EEEEEE")
    win.lblACin.show()

    win.lblACout = QtWidgets.QLabel(win)
    win.lblACout.setText("0W")
    win.lblACout.setGeometry(0, 0, 100, 36)
    win.lblACout.move(286, 42)
    win.lblACout.setFont(font)
    win.lblACout.setStyleSheet("color: #EEEEEE")
    win.lblACout.setAlignment(QtCore.Qt.AlignRight)
    win.lblACout.show()

    win.lblDCout = QtWidgets.QLabel(win)
    win.lblDCout.setText("0W")
    win.lblDCout.setGeometry(0, 0, 100, 36)
    win.lblDCout.move(303, 590)
    win.lblDCout.setFont(font)
    win.lblDCout.setStyleSheet("color: #EEEEEE")
    win.lblDCout.setAlignment(QtCore.Qt.AlignRight)
    win.lblDCout.show()

    pixmap = QPixmap('bluetooth.png')
    win.lblConnectionInfo  = QtWidgets.QLabel(win)
    win.lblConnectionInfo.setGeometry(200, 170, 135, 81)
    win.lblConnectionInfo.setPixmap(pixmap)
    win.lblConnectionInfo.show()


    win.lblBattBar  = QtWidgets.QLabel(win)
    win.lblBattBar.setGeometry(210, 678, 0, 55)
    win.lblBattBar.setStyleSheet("background-color: #AAAAAA")
    win.lblBattBar.show()

    win.lblBattPerc = QtWidgets.QLabel(win)
    win.lblBattPerc.setText("? %")
    win.lblBattPerc.move(208, 689)
    win.lblBattPerc.setFont(font)
    win.lblBattPerc.setStyleSheet("color: #000000")
    win.lblBattPerc.setAlignment(QtCore.Qt.AlignCenter)
    win.lblBattPerc.show()

    pixmap = QPixmap('circleGreen.png')

    win.lblImgDCIn = QtWidgets.QLabel(win)
    win.lblImgDCIn.setGeometry(100, 100, 27, 27)
    win.lblImgDCIn.setPixmap(pixmap)

    win.lblImgDCIn2 = QtWidgets.QLabel(win)
    win.lblImgDCIn2.setGeometry(100, 100, 27, 27)
    win.lblImgDCIn2.setPixmap(pixmap)


    win.lblImgACIn = QtWidgets.QLabel(win)
    win.lblImgACIn.setGeometry(100, 100, 27, 27)
    win.lblImgACIn.setPixmap(pixmap)

    win.lblImgACIn2 = QtWidgets.QLabel(win)
    win.lblImgACIn2.setGeometry(100, 100, 27, 27)
    win.lblImgACIn2.setPixmap(pixmap)


    win.lblImgBatIn = QtWidgets.QLabel(win)
    win.lblImgBatIn.setGeometry(100, 100, 27, 27)
    win.lblImgBatIn.setPixmap(pixmap)

    win.lblImgBatIn2 = QtWidgets.QLabel(win)
    win.lblImgBatIn2.setGeometry(100, 100, 27, 27)
    win.lblImgBatIn2.setPixmap(pixmap)



    pixmap = QPixmap('circleOrange.png')

    win.lblImgDCOut = QtWidgets.QLabel(win)
    win.lblImgDCOut.setGeometry(100, 100, 27, 27)
    win.lblImgDCOut.setPixmap(pixmap)

    win.lblImgDCOut2 = QtWidgets.QLabel(win)
    win.lblImgDCOut2.setGeometry(100, 100, 27, 27)
    win.lblImgDCOut2.setPixmap(pixmap)


    win.lblImgACOut = QtWidgets.QLabel(win)
    win.lblImgACOut.setGeometry(100, 100, 27, 27)
    win.lblImgACOut.setPixmap(pixmap)

    win.lblImgACOut2 = QtWidgets.QLabel(win)
    win.lblImgACOut2.setGeometry(100, 100, 27, 27)
    win.lblImgACOut2.setPixmap(pixmap)


    win.lblImgBatOut = QtWidgets.QLabel(win)
    win.lblImgBatOut.setGeometry(100, 100, 27, 27)
    win.lblImgBatOut.setPixmap(pixmap)

    win.lblImgBatOut2 = QtWidgets.QLabel(win)
    win.lblImgBatOut2.setGeometry(100, 100, 27, 27)
    win.lblImgBatOut2.setPixmap(pixmap)


    #Graph area
    win.gviewSolarInW = QtWidgets.QLabel(win)
    win.gviewSolarInW.setGeometry(510, 00, 450, 148)
    win.gviewSolarInW.show()

    win.gviewDCOutW = QtWidgets.QLabel(win)
    win.gviewDCOutW.setGeometry(510, (10 + 148) * 1, 450, 148)
    win.gviewDCOutW.show()

    win.gviewACOutW = QtWidgets.QLabel(win)
    win.gviewACOutW.setGeometry(510, (10 + 148) * 2, 450, 148)
    win.gviewACOutW.show()

    win.gviewBattPerc = QtWidgets.QLabel(win)
    win.gviewBattPerc.setGeometry(510, (10 + 148) * 3, 450, 148)
    win.gviewBattPerc.show()

    win.gviewBattIO = QtWidgets.QLabel(win)
    win.gviewBattIO.setGeometry(510, (10 + 148) * 4, 450, 148)
    win.gviewBattIO.show()

    #Stats text area
    font.setPointSize(14)
    font.setBold(False)
    win.lblStatSolarWhCaption = QtWidgets.QLabel(win)
    win.lblStatSolarWhCaption.setText("Solar in total:")
    win.lblStatSolarWhCaption.setGeometry(975, 5, 200, 25)
    win.lblStatSolarWhCaption.setFont(font)
    win.lblStatSolarWhCaption.show()

    win.lblStatACInWhCaption = QtWidgets.QLabel(win)
    win.lblStatACInWhCaption.setText("AC in total:")
    win.lblStatACInWhCaption.setGeometry(975, 75, 200, 25)
    win.lblStatACInWhCaption.setFont(font)
    win.lblStatACInWhCaption.show()

    win.lblStatDCOutWhCaption = QtWidgets.QLabel(win)
    win.lblStatDCOutWhCaption.setText("DC out total:")
    win.lblStatDCOutWhCaption.setGeometry(975, 145, 200, 25)
    win.lblStatDCOutWhCaption.setFont(font)
    win.lblStatDCOutWhCaption.show()

    win.lblStatACOutWhCaption = QtWidgets.QLabel(win)
    win.lblStatACOutWhCaption.setText("AC out total:")
    win.lblStatACOutWhCaption.setGeometry(975, 215, 200, 25)
    win.lblStatACOutWhCaption.setFont(font)
    win.lblStatACOutWhCaption.show()

    win.lblStatBatInCaption = QtWidgets.QLabel(win)
    win.lblStatBatInCaption.setText("Battery in total:")
    win.lblStatBatInCaption.setGeometry(975, 285, 200, 25)
    win.lblStatBatInCaption.setFont(font)
    win.lblStatBatInCaption.show()

    win.lblStatBatOutWhCaption = QtWidgets.QLabel(win)
    win.lblStatBatOutWhCaption.setText("Battery out total:")
    win.lblStatBatOutWhCaption.setGeometry(975, 355, 200, 25)
    win.lblStatBatOutWhCaption.setFont(font)
    win.lblStatBatOutWhCaption.show()

    win.lblStatSolMaxCaption = QtWidgets.QLabel(win)
    win.lblStatSolMaxCaption.setText("Solar W maximum:")
    win.lblStatSolMaxCaption.setGeometry(975, 425, 200, 25)
    win.lblStatSolMaxCaption.setFont(font)
    win.lblStatSolMaxCaption.show()

    win.lblStatSolAvgCaption = QtWidgets.QLabel(win)
    win.lblStatSolAvgCaption.setText("Solar W average:")
    win.lblStatSolAvgCaption.setGeometry(975, 495, 200, 25)
    win.lblStatSolAvgCaption.setFont(font)
    win.lblStatSolAvgCaption.show()

    win.lblStatConTimeCaption = QtWidgets.QLabel(win)
    win.lblStatConTimeCaption.setText("Connection time:")
    win.lblStatConTimeCaption.setGeometry(975, 565, 200, 25)
    win.lblStatConTimeCaption.setFont(font)
    win.lblStatConTimeCaption.show()

    font.setPointSize(24)
    win.lblStatSolarWhVal = QtWidgets.QLabel(win)
    win.lblStatSolarWhVal.setText("0.0 Wh")
    win.lblStatSolarWhVal.setGeometry(975, 30, 200, 25)
    win.lblStatSolarWhVal.setFont(font)
    win.lblStatSolarWhVal.show()

    win.lblStatACInWhVal = QtWidgets.QLabel(win)
    win.lblStatACInWhVal.setText("0.0 Wh")
    win.lblStatACInWhVal.setGeometry(975, 100, 200, 25)
    win.lblStatACInWhVal.setFont(font)
    win.lblStatACInWhVal.show()

    win.lblStatDCOutWhVal = QtWidgets.QLabel(win)
    win.lblStatDCOutWhVal.setText("0.0 Wh")
    win.lblStatDCOutWhVal.setGeometry(975, 170, 200, 25)
    win.lblStatDCOutWhVal.setFont(font)
    win.lblStatDCOutWhVal.show()

    win.lblStatACOutWhVal = QtWidgets.QLabel(win)
    win.lblStatACOutWhVal.setText("0.0 Wh")
    win.lblStatACOutWhVal.setGeometry(975, 240, 200, 25)
    win.lblStatACOutWhVal.setFont(font)
    win.lblStatACOutWhVal.show()

    win.lblStatBatInWhVal = QtWidgets.QLabel(win)
    win.lblStatBatInWhVal.setText("0.0 Wh")
    win.lblStatBatInWhVal.setGeometry(975, 310, 200, 25)
    win.lblStatBatInWhVal.setFont(font)
    win.lblStatBatInWhVal.show()

    win.lblStatBatOutWhVal = QtWidgets.QLabel(win)
    win.lblStatBatOutWhVal.setText("0.0 Wh")
    win.lblStatBatOutWhVal.setGeometry(975, 380, 200, 25)
    win.lblStatBatOutWhVal.setFont(font)
    win.lblStatBatOutWhVal.show()

    win.lblStatSolMaxVal = QtWidgets.QLabel(win)
    win.lblStatSolMaxVal.setText("0 W")
    win.lblStatSolMaxVal.setGeometry(975, 450, 200, 25)
    win.lblStatSolMaxVal.setFont(font)
    win.lblStatSolMaxVal.show()

    win.lblStatSolAvgVal = QtWidgets.QLabel(win)
    win.lblStatSolAvgVal.setText("0.0 W")
    win.lblStatSolAvgVal.setGeometry(975, 520, 200, 25)
    win.lblStatSolAvgVal.setFont(font)
    win.lblStatSolAvgVal.show()

    win.lblStatConTimeVal = QtWidgets.QLabel(win)
    win.lblStatConTimeVal.setText("00:00")
    win.lblStatConTimeVal.setGeometry(975, 590, 200, 25)
    win.lblStatConTimeVal.setFont(font)
    win.lblStatConTimeVal.show()

    #settings
    font.setPointSize(14)
    font.setBold(False)
    win.lblChargWarnCaption = QtWidgets.QLabel(win)
    win.lblChargWarnCaption.setText("Charge warning %:")
    win.lblChargWarnCaption.setGeometry(975, 660, 200, 25)
    win.lblChargWarnCaption.setFont(font)
    win.lblChargWarnCaption.show()

    win.txtChargeWarn = QtWidgets.QTextEdit(win)
    win.txtChargeWarn.setText(str(chargePercWarning))
    win.txtChargeWarn.setGeometry(975, 685, 180, 25)
    #win.txtChargeWarn.setFont(font)
    win.txtChargeWarn.textChanged.connect(chargeWarnTextChanged)
    win.txtChargeWarn.show()

    win.lblDischargWarnCaption = QtWidgets.QLabel(win)
    win.lblDischargWarnCaption.setText("Discharge warning %:")
    win.lblDischargWarnCaption.setGeometry(975, 730, 200, 25)
    win.lblDischargWarnCaption.setFont(font)
    win.lblDischargWarnCaption.show()

    win.txtDischhargeWarn = QtWidgets.QTextEdit(win)
    win.txtDischhargeWarn.setText(str(dischargePercWarning))
    win.txtDischhargeWarn.setGeometry(975, 755, 180, 25)
    win.txtDischhargeWarn.textChanged.connect(dischargeWarnTextChanged)
    win.txtDischhargeWarn.show()


    win.txtChargeWarn.clearFocus()

    #Timers
    timer = QTimer(win)
    timer.timeout.connect(animateGui)
    timer.start(20)

    timer2 = QTimer(win)
    timer2.timeout.connect(lowFreqTimer)
    timer2.start(1000)

    drawAllGraphs()

toggleBluetoothBlink = 0
def lowFreqTimer():
    global connected, toggleBluetoothBlink
    if connected == True:
        if time.time() - lastconnectionTime > 10.0:
            connected = False
        else:
            win.lblConnectionInfo.hide()

    if connected == False:
        toggleBluetoothBlink += 1
        if toggleBluetoothBlink > 1:
            win.lblConnectionInfo.show()
            toggleBluetoothBlink = 0
        else:
            win.lblConnectionInfo.hide()


def secToTimeText(sec):
    return ("00" + str(int(sec / 60)))[-2:] + ":" + ("00" + str(int(sec) % 60))[-2:]

lastRefreshGui = 0.0
def refreshGui():
    global win, bdata, lastRefreshGui

    if time.time() - lastRefreshGui < 1.0:
        return

    lastRefreshGui = time.time()

    win.lblDCout.setText(str(bdata.dcOutWatts) + "W")
    win.lblDCin.setText(str(bdata.dcInWatts) + "W")
    win.lblACout.setText(str(bdata.acOutWatts) + "W")
    win.lblACin.setText(str(bdata.acInWatts) + "W")
    win.lblBattPerc.setText(str(bdata.batteryPerc) + "%")
    win.lblBattBar.setGeometry(210, 681, int(bdata.batteryPerc * 95 / 100), 55)
    win.lblBattBar.setStyleSheet("background-color: " + getColorCodeFromPerc(bdata.batteryPerc))

    win.lblStatSolarWhVal.setText(str(round(bdata.wattHInDCSum, 2)) + " Wh")
    win.lblStatACInWhVal.setText(str(round(bdata.wattHInACSum, 2)) + " Wh")
    win.lblStatACOutWhVal.setText(str(round(bdata.wattHOutACSum, 2)) + " Wh")
    win.lblStatDCOutWhVal.setText(str(round(bdata.wattHOutDCSum, 2)) + " Wh")
    win.lblStatBatInWhVal.setText(str(round(bdata.batInWh, 2)) + " Wh")
    win.lblStatBatOutWhVal.setText(str(round(bdata.batOutWh, 2)) + " Wh")
    win.lblStatSolMaxVal.setText(str(bdata.solarMaxW) + " W")
    if bdata.solarWAvgCnt > 0:
        win.lblStatSolAvgVal.setText(str(round(float(bdata.solarWAvgSum) / bdata.solarWAvgCnt, 2)) + " W")
    win.lblStatConTimeVal.setText(secToTimeText(bdata.connectTime / 60.0))


def chargeWarnTextChanged():
    global chargePercWarning
    try:
        chargePercWarning =  int(win.txtChargeWarn.toPlainText())
    except:
        pass

def dischargeWarnTextChanged():
    global dischargePercWarning
    try:
        dischargePercWarning =  int(win.txtDischhargeWarn.toPlainText())
    except:
        pass


def getColorCodeFromPerc(perc):
    clr = getColorFromPerc(perc)
    return '#%02x%02x%02x' % (int(clr.red()), int(clr.green()), 32)

def getColorFromPerc(perc):
    r = 0
    g = 0
    if (perc < 50):
        r = 230
        #g = perc / 50 * 230
        g = max((perc - 10) / 40 * 230, 0)
    if (perc >= 50):
        g = 230
        #r = (100 - perc) / 50 * 230
        r = max(((100 - perc) - 10) / 40 * 230, 0)

    return QColor(int(r), int(g), 32)

def convProgressToPos(progress, powerline):
    if powerline == 0:
        p = progress % 1000
        if p < 680:
            retX = 51
            retY = 100 + p / 3.7;
        if p >= 660 and p < 700:
            retX = 56 + math.sin((40 - p - 660) / 40.0 * -1.57075 + 4.71) * 5.0
            retY = 279 + math.cos((40 - p - 660) / 40.0 * -1.57075 + 4.71) * 5.0
        if p >= 700:
            retX = 51 + (p - 680)  / 3.7;
            retY = 284;
        return retX, retY

    if powerline == 1:
        p = progress % 1000
        if p < 680:
            retX = 51
            retY = 543 - p / 3.7;
        if p >= 660 and p < 700:
            retX = 56 + math.sin((40 - p - 660) / 40.0 * 1.57075 + 4.71) * 5.0
            retY = 365 + math.cos((40 - p - 660) / 40.0 * 1.57075 +4.71) * 5.0
        if p >= 700:
            retX = 51 + (p - 680)  / 3.7;
            retY = 360

        return retX, retY



    if powerline == 2:
        p = progress % 1000
        p = 1000 - p
        if p < 680:
            retX = 422
            retY = 100 + p / 3.7;
        if p >= 660 and p < 700:
            retX = 417 - math.sin((40 - p - 660) / 40.0 * -1.57075 + 4.71) * 5.0
            retY = 279 + math.cos((40 - p - 660) / 40.0 * -1.57075 + 4.71) * 5.0
        if p >= 700:
            retX = 422 - (p - 680)  / 3.7;
            retY = 284;
        return retX, retY

    if powerline == 3:
        p = progress % 1000
        p = 1000 - p
        if p < 680:
            retX = 422
            retY = 543 - p / 3.7;
        if p >= 660 and p < 700:
            retX = 417 - math.sin((40 - p - 660) / 40.0 * 1.57075 + 4.71) * 5.0
            retY = 365 + math.cos((40 - p - 660) / 40.0 * 1.57075 +4.71) * 5.0
        if p >= 700:
            retX = 422 - (p - 680)  / 3.7;
            retY = 360
        return retX, retY

    if powerline == 4:
        p = progress % 863
        retX = 229
        retY = 407 + p / 3.7
        return retX, retY

    if powerline == 5:
        p = progress % 863
        retX = 253
        retY = 407 + (863 - p) / 3.7
        return retX, retY



lastAnimationTime = time.time()
#tempx = 600
def animateGui():
    global tempx, lastAnimationTime, updateGUI

    if updateGUI == True:
        updateGUI = False
        refreshGui()



    timeDelta = time.time() - lastAnimationTime
    x = 0.0
    y = 0.0

    #DC In
    guiProgVals[0] += bdata.dcInWatts * timeDelta * 7
    if (bdata.dcInWatts > 0):
        x, y = convProgressToPos(guiProgVals[0], 0)
        win.lblImgDCIn.move(int(x), int(y))
        x, y = convProgressToPos(guiProgVals[0] + 500, 0)
        win.lblImgDCIn2.move(int(x), int(y))
        if guiProgVis[0] == False:
            guiProgVis[0] = True
            win.lblImgDCIn.show()
            win.lblImgDCIn2.show()
    else:
        if guiProgVis[0] == True:
                guiProgVis[0] = False
                win.lblImgDCIn.hide()
                win.lblImgDCIn2.hide()


    #AC In
    guiProgVals[1] += bdata.acInWatts * timeDelta * 7
    if (bdata.acInWatts > 0):
        x, y = convProgressToPos(guiProgVals[1], 1)
        win.lblImgACIn.move(int(x), int(y))
        x, y = convProgressToPos(guiProgVals[1] + 500, 1)
        win.lblImgACIn2.move(int(x), int(y))
        if guiProgVis[1] == False:
            guiProgVis[1] = True
            win.lblImgACIn.show()
            win.lblImgACIn2.show()
    else:
        if guiProgVis[1] == True:
                guiProgVis[1] = False
                win.lblImgACIn.hide()
                win.lblImgACIn2.hide()

    #AC out
    guiProgVals[2] += bdata.acOutWatts * timeDelta * 7
    if (bdata.acOutOn == True):
        x, y = convProgressToPos(guiProgVals[2], 2)
        win.lblImgACOut.move(int(x), int(y))
        x, y = convProgressToPos(guiProgVals[2] + 500, 2)
        win.lblImgACOut2.move(int(x), int(y))
        if guiProgVis[2] == False:
            guiProgVis[2] = True
            win.lblImgACOut.show()
            win.lblImgACOut2.show()
    else:
        if guiProgVis[2] == True:
                guiProgVis[2] = False
                win.lblImgACOut.hide()
                win.lblImgACOut2.hide()


    #DC out
    guiProgVals[3] += bdata.dcOutWatts * timeDelta * 7
    if (bdata.dcOutOn == True or bdata.dcOutWatts > 0):
        x, y = convProgressToPos(guiProgVals[3], 3)
        win.lblImgDCOut.move(int(x), int(y))
        x, y = convProgressToPos(guiProgVals[3] + 500, 3)
        win.lblImgDCOut2.move(int(x), int(y))
        if guiProgVis[3] == False:
            guiProgVis[3] = True
            win.lblImgDCOut.show()
            win.lblImgDCOut2.show()
    else:
        if guiProgVis[3] == True:
                guiProgVis[3] = False
                win.lblImgDCOut.hide()
                win.lblImgDCOut2.hide()



    #Bat in
    guiProgVals[4] += bdata.batInOutWatts * timeDelta * 7
    if (bdata.batInOutWatts > 0):
        x, y = convProgressToPos(guiProgVals[4], 4)
        win.lblImgBatIn.move(int(x), int(y))
        x, y = convProgressToPos(guiProgVals[4] + 432, 4)
        win.lblImgBatIn2.move(int(x), int(y))
        if guiProgVis[4] == False:
            guiProgVis[4] = True
            win.lblImgBatIn.show()
            win.lblImgBatIn2.show()
    else:
        if guiProgVis[4] == True:
                guiProgVis[4] = False
                win.lblImgBatIn.hide()
                win.lblImgBatIn2.hide()



    #Bat out
    guiProgVals[5] += (-bdata.batInOutWatts) * timeDelta * 7
    if (bdata.batInOutWatts < 0):
        x, y = convProgressToPos(guiProgVals[5], 5)
        win.lblImgBatOut.move(int(x), int(y))
        x, y = convProgressToPos(guiProgVals[5] + 432, 5)
        win.lblImgBatOut2.move(int(x), int(y))
        if guiProgVis[5] == False:
            guiProgVis[5] = True
            win.lblImgBatOut.show()
            win.lblImgBatOut2.show()
    else:
        if guiProgVis[5] == True:
                guiProgVis[5] = False
                win.lblImgBatOut.hide()
                win.lblImgBatOut2.hide()


    lastAnimationTime = time.time()

def findMaximum(arr):
    maxV = 0
    for a in arr:
        if a > maxV:
            maxV = a
        if abs(a) > maxV:
            maxV = abs(a)
    return maxV

def findPerfectScale(maxV):
    if maxV < 1:
        return 0.1
    if maxV < 5:
        return 1.0
    if maxV < 20:
        return 5
    if maxV < 100:
        return 10
    if maxV < 500:
        return 50
    if maxV < 1000:
        return 100
    if maxV < 5000:
        return 500
    return 1000



def prepareGraph(graphicsView, title, yTxt, plotData, color, minScale):
    w = graphicsView.width()
    h = graphicsView.height()
    maxV = max(minScale, findMaximum(plotData))


    pixmap = QPixmap(QSize(w, h))
    painter = QPainter(pixmap)

    line = QPen()
    line.setColor(QColor(0, 0, 0))
    line.setWidth(1)

    painter.setPen(line)
    painter.setRenderHint(QPainter.Antialiasing, True)

    pixmap.fill(QColor(255, 250, 240))

    painter.drawLine(20, h - 10, w - 10, h - 10)
    painter.drawLine(20, 10, 20, h - 10)

    font = QFont("Verdana", 12)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(40, 12, title)

    font = QFont("Verdana", 8)
    font.setBold(False)
    painter.setFont(font)
    painter.drawText(15, 8, yTxt)
    painter.drawText(w - 8, h - 8, "t")


    line.setColor(QColor(192, 192, 192))
    painter.setPen(line)

    scale = findPerfectScale(maxV)
    pxPerUnitHeight = maxV / (h - 20)

    if int(scale) > 0:
        for yPos in range(int(scale), int(maxV + scale), int(scale)):
            painter.drawLine(20, int(h - 10 - yPos / pxPerUnitHeight), w - 10, int(h - 10 - yPos / pxPerUnitHeight))
            painter.drawText(0, int(h - 6 - yPos / pxPerUnitHeight), str(yPos))


    shiftVals = 0
    shrinkFactor = 1.0
    if len(plotData) > w - 30:
        #shiftVals = len(plotData) - (w - 30) ## shifting graph to left
        shrinkFactor = (w - 30) / len(plotData) ##shrinking the graph

    for i in range(shiftVals, len(newHourHistory)):
        si = int(i * shrinkFactor)
        if (newHourHistory[i] > 0):
            painter.drawLine(20 + si - shiftVals, h - 10, 20 + si - shiftVals, 10)
            painter.drawText(20 + si - shiftVals, h - 0, str(newHourHistory[i]) +":00")

    if color == 0:
        line.setColor(QColor(32, 192, 32))
    if color == 1:
        line.setColor(QColor(192, 32, 32))
    if color == 2:
        line.setColor(QColor(32, 32, 192))
    painter.setPen(line)


    prevSi = -1
    tempValSum = 0.0
    tempValCnt = 0
    if pxPerUnitHeight > 0:
        for i in range(shiftVals, len(plotData)):
            si = int(i * shrinkFactor)
            tempValSum += plotData[i]
            tempValCnt += 1
            if si == prevSi:
                continue
            prevSi = si

            avgVal = tempValSum / tempValCnt
            dVal = avgVal
            if color == 3:
                if dVal < 0:
                    line.setColor(QColor(192, 32, 32))
                    painter.setPen(line)
                    dVal = -dVal
                else:
                    line.setColor(QColor(0, 192, 32))
                    painter.setPen(line)
            if color == 4:
                line.setColor(getColorFromPerc(avgVal))
                painter.setPen(line)

            xPos =  20 + si
            yPos = int(h - 10 - avgVal / pxPerUnitHeight)
            painter.drawLine(20 + si - shiftVals, h - 10, 20 + si - shiftVals, h - 10 - int(dVal / pxPerUnitHeight))
            tempValSum = 0.0
            tempValCnt = 0

    painter.end()
    graphicsView.setPixmap(pixmap)


def drawAllGraphs():
    prepareGraph(win.gviewSolarInW, "Solar Watts", "W", solarInHistory, 0, 20)
    prepareGraph(win.gviewDCOutW, "DC Out Watts", "W", DCOutHistory, 1, 20)
    prepareGraph(win.gviewACOutW, "AC Out Watts", "W", ACOutHistory, 1, 20)
    prepareGraph(win.gviewBattPerc, "Battery %", "%", battPercHistory, 4, 100)
    prepareGraph(win.gviewBattIO, "Battery I/O Watts", "W", battInOutHistory, 3, 20)



    pass

def main():

    sys.exit(app.exec_())



mp = vlc.MediaPlayer('notify.mp3')

if __name__ == "__main__":

    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowIcon(QIcon("example.png"))
    win.show()

    loggerThread = threading.Thread(target = initLogging)
    loggerThread.start()


    initWindow(win)


    main()
    exitFlag = True
