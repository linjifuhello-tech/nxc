import sounddevice as sd
import numpy as np
import wave, base64, requests, subprocess
from config import BAIDU_API_KEY, BAIDU_SECRET_KEY, BAIDU_ASR_URL

# 1) 获取百度 Access Token（鉴权）
def get_baidu_token():
    url = ("https://aip.baidubce.com/oauth/2.0/token"
           f"?grant_type=client_credentials&client_id={BAIDU_API_KEY}&client_secret={BAIDU_SECRET_KEY}")
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json().get("access_token")

# 2) 录音（直接录到 16kHz，避免二次转换；）
def record_wav_16k(out_wav="recorded.wav", seconds=6, device=None):
    RATE, CH, WIDTH = 16000, 1, 2  # 16kHz, 单声道, 16bit
    if device is not None:
        sd.default.device = device  # 你的麦克风编号，可省略
    print(f"🎤 录音 {seconds}s @ {RATE}Hz ...")
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=CH, dtype=np.int16)
    sd.wait()
    with wave.open(out_wav, 'wb') as wf:
        wf.setnchannels(CH)
        wf.setsampwidth(WIDTH)  # 16bit = 2 bytes
        wf.setframerate(RATE)
        wf.writeframes(audio.tobytes())
    print("✅ 录音完成:", out_wav)
    return out_wav

# 3) 发送到百度识别
def speech_to_text(wav_path):
    token = get_baidu_token()
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()
    payload = {
        "format": "wav",
        "rate": 16000,          # 采样率要与录音保持一致
        "channel": 1,
        "token": token,
        "cuid": "your-device-id",
        "speech": base64.b64encode(audio_bytes).decode("utf-8"),
        "len": len(audio_bytes),
        "dev_pid": 1537         # 普通话
    }
    r = requests.post(BAIDU_ASR_URL, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
    data = r.json()
    if data.get("err_no") == 0:
        return data["result"][0].strip()
    return None

if __name__ == "__main__":
    wav = record_wav_16k(seconds=6)         # 录 3 秒
    text = speech_to_text(wav)              # 识别
    print("✅ 识别结果：", text)

import requests


# 测试 /chat/ 接口
def test_chat():
    url = "http://localhost:8000/chat/"
    data = {
        "prompt": text,
        "options": {"temperature": 0.7, "max_tokens": 100}
    }
    response = requests.post(url, json=data)
    final_result = response.json().get('response')
    print(final_result)
    print("Response:", response.json())
    return final_result


# 测试 /health 接口
def test_health():
    url = "http://localhost:8000/health"
    response = requests.get(url)
    print("Health Check:", response.json())


if __name__ == "__main__":
    test_chat()
    # test_health()















# baidu_tts.py
from aip import AipSpeech
import urllib.parse


# ---------------------------
# 1. 配置你自己的百度智能云账号信息
# ---------------------------
APP_ID = "119812145"
API_KEY = "p9vdGZYrapwbhRNLVtBos2yi"
SECRET_KEY = "CQxpf1UWJlZEwKbUCfpgKryfbhtGU4hl"

client = AipSpeech(APP_ID, API_KEY, SECRET_KEY)

def baidu_tts(text, out_file="output.mp3", vol=5, spd=5, pit=5, per=0):
    """
    调用百度在线TTS接口，把文字合成语音保存为 MP3 文件
    :param text: 待合成文本（建议<=120字，长文本可自行分段）
    :param out_file: 输出文件名
    :param vol: 音量 [0-15] 默认5
    :param spd: 语速 [0-9] 默认5
    :param pit: 音调 [0-9] 默认5
    :param per: 发音人
                普通：0=度小美(女), 1=度小宇(男), 3=度逍遥, 4=x度丫丫
                精品：5003=度逍遥精品, 5118=度小鹿, 106=度博文, 110=度小童,
                     111=度小萌, 103=度米朵, 5=度小娇
    """
    # 按官方要求再做一次 urlencode（SDK内部已做1次）
    safe_text = urllib.parse.quote_plus(text)

    # 调用合成接口
    result = client.synthesis(
        safe_text,  # 合成的文本
        lang='jp',  # 中文
        ctp=1,      # 客户端类型: 固定值
        options={
            "vol": vol,
            "spd": spd,
            "pit": pit,
            "per": per
        }
    )

    # 如果返回的是二进制音频数据
    if not isinstance(result, dict):
        with open(out_file, "wb") as f:
            f.write(result)
        print(f"✅ 已生成语音文件: {out_file}")
    else:
        # 出错时返回 dict，例如 {"err_no":500,"err_msg":"notsupport."}
        print("❌ 语音合成失败：", result)

if __name__ == "__main__":
    text = test_chat()
    baidu_tts(text, out_file="hello.mp3", per=6567) # 6567











import pygame
import time
import os













def play_audio(file_path):

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在")
        return

    # 初始化pygame音频模块
    pygame.mixer.init()

    try:
        # 加载音频文件
        pygame.mixer.music.load(file_path)
        print(f"正在播放: {file_path}")

        # 开始播放
        pygame.mixer.music.play()

        # 等待播放完成
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        print("播放完成")

    except pygame.error as e:
        print(f"播放错误: {e}")
    finally:
        # 清理资源
        pygame.mixer.quit()


if __name__ == "__main__":
    # 替换为你的音频文件路径
    audio_file = "C:\\Users\\linji\\PyCharmMiscProject\\hello.mp3"
  # 支持mp3, wav等多种格式
    play_audio(audio_file)