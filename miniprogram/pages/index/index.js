const SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
const RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";
const TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";

const PRESETS = [
  { name: "我的专属节奏", speed: 0.8 },
  { name: "沉稳严谨", speed: 1.0 },
  { name: "日常自然", speed: 1.4 },
  { name: "流畅熟练", speed: 1.8 },
  { name: "极速爆发", speed: 2.5 }
];

Page({
  data: {
    connected: false,
    searching: false,
    deviceId: "",
    inputText: "",
    selectedPreset: 0, // 默认开启“我的专属节奏”
    logs: []
  },

  onLoad() {
    this.addLog("小程序已就绪，请点击一键连接");
  },

  onUnload() {
    this.closeBle();
  },

  addLog(msg) {
    const now = new Date();
    const timeStr = String(now.getHours()).padStart(2, '0') + ":" + 
                    String(now.getMinutes()).padStart(2, '0') + ":" + 
                    String(now.getSeconds()).padStart(2, '0');
    const curLogs = this.data.logs || [];
    const newLogs = [{ time: timeStr, msg: msg }].concat(curLogs).slice(0, 30);
    this.setData({ logs: newLogs });
  },

  // ---------------- 蓝牙搜索与连接 ----------------
  toggleConnect() {
    if (this.data.connected) {
      this.closeBle();
    } else {
      this.startScanAndConnect();
    }
  },

  startScanAndConnect() {
    const that = this;
    this.setData({ searching: true });
    this.addLog("正在初始化蓝牙...");

    wx.openBluetoothAdapter({
      success() {
        that.addLog("正在扫描 AutoTyping-BLE...");
        wx.startBluetoothDevicesDiscovery({
          allowDuplicatesKey: false,
          success() {
            that.listenForDevice();
          },
          fail(err) {
            that.addLog("扫描失败: " + err.errMsg);
            that.setData({ searching: false });
          }
        });
      },
      fail(err) {
        wx.showModal({
          title: "提示",
          content: "请开启手机蓝牙并授权微信使用蓝牙！",
          showCancel: false
        });
        that.setData({ searching: false });
      }
    });
  },

  listenForDevice() {
    const that = this;
    wx.onBluetoothDeviceFound((res) => {
      res.devices.forEach((dev) => {
        const name = dev.name || dev.localName || "";
        if (name === "AutoTyping-BLE") {
          that.addLog("发现设备，正在连接...");
          wx.stopBluetoothDevicesDiscovery();
          that.connectToDevice(dev.deviceId);
        }
      });
    });

    setTimeout(() => {
      if (that.data.searching && !that.data.connected) {
        wx.stopBluetoothDevicesDiscovery();
        that.setData({ searching: false });
        that.addLog("搜索超时，请确认板子正常运行");
      }
    }, 12000);
  },

  connectToDevice(deviceId) {
    const that = this;
    wx.createBLEConnection({
      deviceId: deviceId,
      success() {
        that.setData({ connected: true, searching: false, deviceId: deviceId });
        that.addLog("🎉 蓝牙连接成功！正在协商 MTU 并获取通道...");

        // 协商 MTU 到 512 (防止大文本数据导致 1358 字符队列溢出)
        if (wx.setBLEMTU) {
          wx.setBLEMTU({
            deviceId: deviceId,
            mtu: 512,
            success(res) {
              that.addLog("⚡ 传输单元 (MTU) 优化为: " + res.mtu);
              that.mtu = res.mtu;
            },
            fail() {
              that.mtu = 23;
            },
            complete() {
              that.discoverServices(deviceId);
            }
          });
        } else {
          that.mtu = 23;
          that.discoverServices(deviceId);
        }
      },
      fail(err) {
        that.setData({ searching: false });
        that.addLog("连接失败: " + err.errMsg);
      }
    });

    wx.onBLEConnectionStateChange((res) => {
      if (!res.connected) {
        that.setData({ connected: false, deviceId: "" });
        that.addLog("⚠️ 蓝牙已断开");
      }
    });
  },

  discoverServices(deviceId) {
    const that = this;
    wx.getBLEDeviceServices({
      deviceId: deviceId,
      success(res) {
        const targetService = res.services.find(s => s.uuid.toUpperCase().includes("6E400001"));
        if (targetService) {
          that.discoverCharacteristics(deviceId, targetService.uuid);
        } else {
          that.addLog("未找到匹配的服务");
        }
      },
      fail(err) {
        that.addLog("获取服务失败: " + err.errMsg);
      }
    });
  },

  discoverCharacteristics(deviceId, serviceId) {
    const that = this;
    wx.getBLEDeviceCharacteristics({
      deviceId: deviceId,
      serviceId: serviceId,
      success(res) {
        that.serviceId = serviceId;
        res.characteristics.forEach((c) => {
          const u = c.uuid.toUpperCase();
          if (u.includes("6E400002")) {
            that.rxCharId = c.uuid;
          }
          if (u.includes("6E400003")) {
            that.txCharId = c.uuid;
            that.enableTxNotify(deviceId, serviceId, c.uuid);
          }
        });
        that.addLog("✅ 键盘通道就绪，可随时打字！");
      },
      fail(err) {
        that.addLog("获取通道失败: " + err.errMsg);
      }
    });
  },

  enableTxNotify(deviceId, serviceId, charId) {
    const that = this;
    wx.notifyBLECharacteristicValueChange({
      state: true,
      deviceId: deviceId,
      serviceId: serviceId,
      characteristicId: charId,
      success() {
        wx.onBLECharacteristicValueChange((res) => {
          const str = that.arrayBufferToString(res.value);
          that.addLog("板子通知: " + str);
        });
      }
    });
  },

  closeBle() {
    if (this.data.deviceId) {
      wx.closeBLEConnection({ deviceId: this.data.deviceId });
    }
    wx.closeBluetoothAdapter();
    this.setData({ connected: false, searching: false, deviceId: "" });
    this.addLog("蓝牙已断开");
  },

  // ---------------- 文本输入与剪贴板 ----------------
  onTextInput(e) {
    this.setData({ inputText: e.detail.value });
  },

  pasteClipboard() {
    const that = this;
    wx.getClipboardData({
      success(res) {
        if (res.data) {
          that.setData({ inputText: res.data });
          wx.showToast({ title: "已粘贴", icon: "success" });
        }
      }
    });
  },

  clearInput() {
    this.setData({ inputText: "" });
  },

  selectPreset(e) {
    const idx = parseInt(e.currentTarget.dataset.index, 10);
    this.setData({ selectedPreset: idx });
    wx.showToast({ title: "切换: " + PRESETS[idx].name, icon: "none" });
  },

  // ---------------- 发送打字指令 ----------------
  async startTyping() {
    const text = this.data.inputText;
    if (!text) {
      wx.showToast({ title: "请输入文本", icon: "none" });
      return;
    }

    const curPreset = PRESETS[this.data.selectedPreset];

    // 发送档位切换指令: [P:idx] (0~4)
    await this.writeRawString("[P:" + this.data.selectedPreset + "]");
    await this.sleep(40);

    // 直接分包发送正文
    this.addLog("开始下发 (" + text.length + " 字符 | " + curPreset.name + ")...");
    await this.sendLargeText(text);

    wx.showToast({ title: "已全部发送！", icon: "success" });
  },

  async pauseTyping() {
    await this.writeRawString("pause");
    this.addLog("已发送暂停");
  },

  async resumeTyping() {
    await this.writeRawString("resume");
    this.addLog("已发送继续");
  },

  async stopTyping() {
    await this.writeRawString("stop");
    this.addLog("已发送中止");
  },

  // ---------------- 分包下发 (带动态 MTU 与防拥塞流控) ----------------
  async sendLargeText(str) {
    const buffer = this.stringToArrayBuffer(str);
    const totalBytes = buffer.byteLength;
    // 如果协商到大 MTU 则单包发 128 字节，否则使用保守标准的 20 字节
    const chunkSize = (this.mtu && this.mtu > 100) ? 128 : 20;
    this.addLog(`开始分包传输，共 ${totalBytes} 字节 (单包 ${chunkSize} 字节)...`);

    for (let offset = 0; offset < totalBytes; offset += chunkSize) {
      const slice = buffer.slice(offset, offset + chunkSize);
      let success = false;

      // 最多重试 3 次，防止系统 BLE 驱动发送队列排空延迟导致丢包断流
      for (let retry = 0; retry < 3; retry++) {
        success = await this.writeChunk(slice);
        if (success) break;
        this.addLog(`⚠️ 分包写入暂缓，第 ${retry + 1} 次重试...`);
        await this.sleep(60 * (retry + 1));
      }

      if (!success) {
        this.addLog(`❌ 传输在 ${offset}/${totalBytes} 字节处中断，请重试`);
        wx.showToast({ title: "传输中断", icon: "error" });
        return;
      }

      // 保证底层 iOS / Android 蓝牙发送队列完全排空，彻底杜绝 1358 字节缓冲区堵塞死锁
      await this.sleep(30);

      if (offset % (chunkSize * 8) === 0 || offset + chunkSize >= totalBytes) {
        const percent = Math.min(100, Math.round(((offset + slice.byteLength) / totalBytes) * 100));
        this.addLog(`传输进度: ${percent}% (${Math.min(offset + slice.byteLength, totalBytes)}/${totalBytes})`);
      }
    }
    this.addLog("✅ 所有长文本已完整下发至单片机！");
  },

  writeRawString(str) {
    const buf = this.stringToArrayBuffer(str);
    return this.writeChunk(buf);
  },

  writeChunk(arrayBuffer) {
    const that = this;
    return new Promise((resolve) => {
      if (!that.data.connected || !that.serviceId || !that.rxCharId) {
        that.addLog("发送失败: 蓝牙尚未就绪");
        resolve(false);
        return;
      }
      wx.writeBLECharacteristicValue({
        deviceId: that.data.deviceId,
        serviceId: that.serviceId,
        characteristicId: that.rxCharId,
        value: arrayBuffer,
        success() {
          resolve(true);
        },
        fail(err) {
          that.addLog("写入失败: " + JSON.stringify(err));
          resolve(false);
        }
      });
    });
  },

  stringToArrayBuffer(str) {
    const utf8 = unescape(encodeURIComponent(str));
    const buf = new ArrayBuffer(utf8.length);
    const bufView = new Uint8Array(buf);
    for (let i = 0; i < utf8.length; i++) {
      bufView[i] = utf8.charCodeAt(i);
    }
    return buf;
  },

  arrayBufferToString(buf) {
    if (!buf || buf.byteLength === 0) return "";

    // 1. 优先使用原生 TextDecoder (微信小程序在 iOS/Android 上均原生支持)
    try {
      if (typeof TextDecoder !== "undefined") {
        return new TextDecoder("utf-8").decode(buf);
      }
    } catch (e) {}

    // 2. 兼容兜底方案：将 UTF-8 字节流转为 URI 百分比编码，再用 decodeURIComponent 正确解析为中文字符串
    try {
      let encoded = "";
      const u8 = new Uint8Array(buf);
      for (let i = 0; i < u8.length; i++) {
        encoded += "%" + u8[i].toString(16).padStart(2, "0");
      }
      return decodeURIComponent(encoded);
    } catch (e) {
      // 3. 极端乱码兜底
      let result = "";
      const u8 = new Uint8Array(buf);
      for (let i = 0; i < u8.length; i++) {
        result += String.fromCharCode(u8[i]);
      }
      return result;
    }
  },

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
});
