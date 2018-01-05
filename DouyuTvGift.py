# -*- coding: utf-8 -*-

import socket
import subprocess
import xlsxwriter
import signal
import os
import time
import argparse
import requests
from threading import Thread


class DouyuTvGift:
    """记录直播间礼物信息并录制

    Attributes:
        __room_name: 初始传入的房间id，可能为别名，作为文件名的一部分.
        __room_id: 房间id.
        __time_last: 总的记录时长.
        __sock: socket对象.
        __gift: 礼物类型字典.
        __buf: 弹幕池.
        __done: 状态信息.
        __time_start: 视频开始录制时间.
    """

    def __init__(self, room_id, time_last):
        self.__room_name = room_id
        self.__room_id = room_id
        self.__time_start = time_last
        self.__sock = None
        self.__gift = {}
        self.__buf = []
        self.__done = False
        self.__time_last = time_last
        self.__init_connection()

    def __init_connection(self):
        """连接至弹幕服务器"""

        # 判断主播是否开播
        resp = requests.get("http://open.douyucdn.cn/api/RoomApi/room/%s" % args.room_id)
        if not resp.json()['error'] == 0:
            print("连接服务器失败，请重试")
            return
        if resp.json()['data']['room_status'] == "2":
            print("主播未在直播")
            return  # 关播则退出

        # 更新roomid为数字id
        self.__room_id = resp.json()['data']['room_id']

        # 获取礼物的id与name/price的对应关系
        gifts = resp.json()['data']['gift']
        for gift in gifts:
            gfid = str(gift['id'])
            name = gift['name']
            price = gift['pc']
            if gift['type'] == "2":
                price = str(price) + '元'
            else:
                price = str(price) + '鱼丸'
            self.__gift[gfid] = {
                'name': name,
                'price': price
            }

        # 建立TCP连接
        sock = socket.socket()  # 召唤一个邮差
        self.__sock = sock  # 把邮差当作属性，让他更长久地存在
        host = 'openbarrage.douyutv.com'
        port = 8601
        sock.connect((host, port))  # 告诉邮差对方是谁

        # 发送登录请求
        login_req = {
            'type': 'loginreq',
            'roomid': self.__room_id
        }
        self.__send_packet(login_req)  # 完成JSON obeject -> String -> Binary -> Server 的所有工作

        # 监听服务器发回的登录回复
        while True:
            data = sock.recv(2048)  # 拿到邮差手里的消息
            # 看拿到的消息是否是登录响应消息
            if int.from_bytes(data[8:10], byteorder='little') == 690:  # 判断消息是否是由弹幕服务器发送的
                login_res = self.depacket(data)
                # 发送弹幕入组请求
                if login_res['type'] == 'loginres':
                    self.__send_packet({
                        'type': 'joingroup',
                        'rid': self.__room_id,
                        'gid': -9999
                    })
                    # 创建多个线程并开始执行
                    Thread(target=self.__send_heartbeat, name='Send_Heartbeat').start()
                    Thread(target=self.__record_stream, name="Record_Stream").start()
                    Thread(target=self.__recv_danmaku, name='Recv_Danmaku').start()
                    Thread(target=self.__record_gift, name='Record_Gift').start()
                    # 在输入的时间后停止运行
                    time.sleep(self.__time_last * 60)
                    self.__stop()
                    break

    def __record_stream(self):
        """录制直播视频到本地"""

        print(">>> 准备开始录制直播视频...")

        # 获取房间号和当前时间（作为文件名）
        roomid = self.__room_id
        self.__time_start = time.time()
        record_name = "[%s]" % self.__room_name + time.strftime("%Y-%m-%d@%H-%M-%S", time.localtime(self.__time_start))

        # 若当前目录不存在result文件夹则创建
        if not os.path.exists("./result"):
            os.makedirs("./result")

        # 使用shell指令运行streamlink录制直播视频
        cmd = """streamlink https://www.douyu.com/%s worst -o "./result/%s.mp4" --plugin-dirs "./" -f""" % (roomid,
                                                                                                            record_name)
        try:
            record = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # 停止录制
            while not self.__done:
                pass
            print(">>> 直播录制即将停止...")
            record.send_signal(signal.CTRL_C_EVENT)
            print(">>> 直播录制已经停止")
        except KeyboardInterrupt:
            pass

    def __record_gift(self):
        """将暂存区中的礼物信息保存至本地"""

        # 等待文件名称被创建
        while self.__time_start is None:
            pass
        # 新建xlsx文件
        record_name = "[%s]" % self.__room_name + time.strftime("%Y-%m-%d@%H-%M-%S", time.localtime(self.__time_start))
        workbook = xlsxwriter.Workbook('./result/%s.xlsx' % record_name)
        worksheet = workbook.add_worksheet()
        # 写首行
        worksheet.write(0, 0, 'Name')
        worksheet.write(0, 1, 'Count')
        worksheet.write(0, 2, 'Price')
        worksheet.write(0, 3, 'Time')
        worksheet.write(0, 4, 'Offset')
        # 写礼物信息
        row = 1
        col = 0
        while not self.__done or len(self.__buf) > 0:
            if len(self.__buf) > 0:
                gift = self.__buf.pop(0)
                for info in gift:
                    worksheet.write(row, col, info)
                    col += 1
                row += 1
                col = 0
        # 结束写文件
        workbook.close()
        print(">>> 礼物信息已记录完毕")

    def __recv_danmaku(self):
        """接收来自弹幕服务器的消息"""

        # 等待直播录制开始
        print(">>> 礼物获取已就绪，等待直播录制开始...")
        self.__wait_record_start()
        print(">>> 开始记录礼物信息")

        # 接收服务器的消息
        while not self.__done:
            try:
                data = self.__sock.recv(2048)
                if int.from_bytes(data[8:10], byteorder='little') == 690:
                    try:
                        msg = self.depacket(data)
                        if msg['type'] == 'dgb':  # 礼物消息
                                # 获得需要记录的礼物相关信息
                                timestamp = time.time()  # 收到礼物的时间
                                t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))  # 人类易读的日期格式
                                offset = int(timestamp - self.__time_start)  # 和视频开始时间的差距
                                gfid = str(msg['gfid'])
                                name = self.__gift[gfid]['name']
                                price = self.__gift[gfid]['price']
                                try:
                                    count = msg['gfcnt']
                                except KeyError:
                                    count = 1
                                # 将信息保存到缓存区中
                                self.__buf.append([name, count, price, t, offset])
                                t = time.strftime("%H:%M:%S", time.localtime(timestamp))
                                print('[%s] @%s 送出礼物 %s%s个, 单个价值%s' % (t, msg['nn'], name, count, price))
                        elif msg['type'] == 'bc_buy_deserve':  # 酬勤消息
                            # 获得需要记录的礼物信息
                            timestamp = time.time()
                            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))  # 人类易读的日期格式
                            offset = int(timestamp - self.__time_start)
                            name = [None, "初级酬勤", "中级酬勤", "高级酬勤"]
                            price = [None, "15元", "30元", "50元"]
                            lev = msg['lev']
                            self.__buf.append([name[lev], msg['cnt'], price[lev], t, offset])
                    except (KeyError, UnicodeDecodeError):
                        pass
            except ConnectionAbortedError:
                pass  # 跳过当task已经完成后程序仍阻塞在此处的情况

    def __wait_record_start(self):
        """等待直播视频录制文件被创建（录制开始）"""
        record_name = "[%s]" % self.__room_name + time.strftime("%Y-%m-%d@%H-%M-%S", time.localtime(self.__time_start))\
                                                + '.mp4'
        try:
            while record_name not in os.listdir('./result'):
                pass
        except FileNotFoundError:  # 当前目录下result文件夹可能未被创建
            pass

        self.__time_start = time.time()  # 录制开始的真正时间
        print(">>> 直播录制已经开始!")

    def __send_heartbeat(self):
        """定时发送心跳包"""
        while not self.__done:  # 在self.__done为真之前一直重复执行后面的代码
            self.__send_packet({
                'type': 'mrkl'
            })
            time.sleep(45)

    def __send_packet(self, msg):
        """从string构建TCP包并通过Socket发送"""
        self.__sock.send(DouyuTvGift.packet(msg))

    def __stop(self):
        """停止爬取"""
        self.__done = True
        self.__sock.close()

    @staticmethod
    def sst_serialize(info):
        """SST序列化"""
        def rep(part):
            return str(part).replace('/', '@S').replace('@', '@A')

        result = ''
        for key in info.keys():
            result += rep(key) + '@=' + rep(info[key]) + '/'
        return result + '\0'

    @staticmethod
    def packet(message):
        """按照固定格式构建协议包"""
        message = DouyuTvGift.sst_serialize(message)
        msg_len = (8 + len(message)).to_bytes(4, byteorder='little')
        msg_type = (689).to_bytes(2, byteorder='little')
        unused = (0).to_bytes(2, byteorder='little')
        return msg_len + msg_len + msg_type + unused + bytes(message, encoding='utf-8')

    @staticmethod
    def depacket(pkt):
        """从服务器发送的包中提取消息"""
        res = {}
        msg_len = int.from_bytes(pkt[:4], byteorder='little') - 8
        data = pkt[12:12 + msg_len - 2].decode('utf-8').split('/')
        for i in range(0, len(data)):
            pair = data[i].split('@=')
            key = pair[0].replace('@S', '/').replace('@A', '@')
            val = pair[1].replace('@S', '/').replace('@A', '@')
            res[key] = val
        return res


if __name__ == '__main__':
    # 从命令行输入参数 argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('room_id', help='ID of room')
    parser.add_argument('time', type=int, help='Minutes to record')
    args = parser.parse_args()

    if args.time < 1:
        print("时长至少为一分钟")
        exit(0)

    # 新建一个instance
    danmaku = DouyuTvGift(args.room_id, args.time)
