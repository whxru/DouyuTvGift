# DouyuTvGift

录制斗鱼直播视频同时统计在录制过程中主播收到的礼物情况。

## 使用

1. 安装依赖包` requests` ` streamlink` `xlsxwriter`

* Linux/macOS:

```
pip3 install requests streamlink xlsxwriter
```

* Windows:

```
py -3 -m pip install requests streamlink xlsxwriter
```

2. 下载脚本

```
git clone https://github.com/whxru/DouyuTvGift.git
```

3. 运行脚本

* Linux/macOS:

```
python3 DouyuTvGift.py <room_id> <time_to_record>
```

* Windows:

```
py -3 DouyuTvGift.py <room_id> <time_to_record>
```

## 说明

1. 录制的视频和礼物统计文件均在当前目录的result文件夹下，文件名称格式为`[room_id]20XX-XX-XX@XX-XX-XX.mp4/xlsx` （房间id+录制开始时间+文件后缀名）。

2. 礼物统计信息在表格文件中，表格例为：

   | Name | Count | Price | Time                | Offset |
   | ---- | ----- | ----- | ------------------- | ------ |
   | 赞    | 1     | 0.1元  | 2018-01-05 19:37:18 | 1      |

   五项信息依次为`礼物名称` `赠送数量` `礼物单价` `送出时间` `相对于录制开始的时间` 

3. 每次程序执行最后命令行会输出异常信息，这是由于使用`Ctrl+C`事件使streamlink停止录制导致的，非程序本身异常，但目前暂无更优雅地停止录制的方案，故请忽略之。

4. 由于直播视频延迟和streamlink程序录制前的预准备工作， `Offset` 并不完全准确。