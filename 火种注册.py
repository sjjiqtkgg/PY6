import requests
import base64
import random
import string
import urllib3
from PIL import Image
from io import BytesIO
import pytesseract

# 禁用 SSL 证书警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 全局接口配置 =================
GENERATE_URL = 'https://47.76.166.180/captcha/generate'
VALIDATE_URL = 'https://47.76.166.180/captcha/validate'
REGISTER_URL = 'https://47.76.166.180/users'

# 请求头（与真实 curl 完全一致，补齐 x-app-version / x-device-os）
HEADERS = {
    'User-Agent': 'ktor-client',
    'Accept': 'application/json',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json',
    'x-app-version': '1.1.21',
    'x-device-os': 'Android',
}

# ================= 自定义配置 =================
USERNAME_LEN = 10          # 用户名长度
PASSWORD_LEN = 10          # 密码长度
DEVICEID_LEN = 16          # 设备ID长度
RETRY_TIMES = 3            # 验证码失败重试次数
CHAR_SET = string.ascii_lowercase + string.digits  # 随机字符集

# ================= 工具函数 =================
def random_str(length):
    """生成指定长度的随机字符串（小写字母 + 数字）"""
    return ''.join(random.choice(CHAR_SET) for _ in range(length))


def gen_random_info():
    """生成随机注册信息"""
    return {
        "username": random_str(USERNAME_LEN),
        "password": random_str(PASSWORD_LEN),
        "firstName": None,
        "lastName": None,
        "email": None,
        "appliedReferralCode": None,   # 与 curl 对齐，使用 null
        "deviceId": random_str(DEVICEID_LEN),
    }


# ================= 验证码相关 =================
def get_captcha():
    """获取验证码：返回 captchaId 和 imageBase64"""
    resp = requests.get(GENERATE_URL, headers=HEADERS, timeout=10, verify=False)
    resp.raise_for_status()
    data = resp.json()
    return data['captchaId'], data['imageBase64']


def ocr_captcha(image_base64):
    """Base64 解码 + 图片预处理 + 数字 OCR 识别"""
    image_data = base64.b64decode(image_base64)
    image = Image.open(BytesIO(image_data))
    image = image.convert('L')                                 # 灰度化
    image = image.point(lambda x: 255 if x > 127 else 0, '1')  # 二值化
    code = pytesseract.image_to_string(
        image,
        config='--psm 8 -l eng -c tessedit_char_whitelist=0123456789'
    ).strip()
    return code if code else None


def validate_captcha(captcha_id, user_input):
    """提交验证码验证：返回 (valid, token)"""
    data = {"captchaId": captcha_id, "userInput": user_input}
    resp = requests.post(VALIDATE_URL, headers=HEADERS, json=data, timeout=10, verify=False)
    resp.raise_for_status()
    result = resp.json()
    return result, result.get('token')


# ================= 注册相关 =================
def user_register(captcha_token, register_data):
    """用户注册：携带 captchaToken，不带 Cookie"""
    url = f"{REGISTER_URL}?captchaToken={captcha_token}"
    resp = requests.post(url, headers=HEADERS, json=register_data, timeout=10, verify=False)
    resp.raise_for_status()
    return resp.json()


def single_register_with_retry(reg_info):
    """单次注册（带验证码失败重试），重试满次数则抛异常"""
    for retry in range(1, RETRY_TIMES + 1):
        print(f"🔍 验证码获取/验证 [第{retry}/{RETRY_TIMES}次尝试]")
        try:
            # 1. 获取验证码
            captcha_id, image_b64 = get_captcha()

            # 2. OCR 识别
            code = ocr_captcha(image_b64)
            if not code:
                raise Exception("OCR识别为空，未提取到数字")
            print(f"📝 验证码识别结果: {code}")

            # 3. 提交验证码验证
            validate_result, captcha_token = validate_captcha(captcha_id, code)
            if not validate_result.get('valid'):
                raise Exception(f"验证失败: {validate_result.get('message', '验证不通过')}")

            # 4. 验证通过，开始注册
            print(f"✅ 验证码验证成功，开始注册...")
            reg_result = user_register(captcha_token, reg_info)
            return reg_result

        except Exception as e:
            if retry == RETRY_TIMES:
                raise Exception(f"验证码重试{RETRY_TIMES}次均失败: {str(e)}")
            else:
                print(f"❌ 本次失败: {str(e)}，准备重试...\n")
                continue
    raise Exception("未知错误，注册终止")


# ================= 主程序 =================
if __name__ == '__main__':
    print("===== 账号自动注册脚本 [GitHub Actions 无交互版] =====")

    # 直接写死要注册的账号数量（可根据需要自行修改数字）
    loop_times = 3

    # 初始化统计
    success_count = 0
    fail_count = 0
    fail_list = []

    print(f"\n🚀 开始批量注册【共{loop_times}个账号】，验证码失败最多重试{RETRY_TIMES}次")
    print("=" * 50 + "\n")

    # 循环注册
    for i in range(1, loop_times + 1):
        print(f"========== 处理第{i}/{loop_times}个账号 ==========")
        reg_info = gen_random_info()
        print(f"🎲 随机信息生成：\n  用户名：{reg_info['username']}\n  密码：{reg_info['password']}\n  设备ID：{reg_info['deviceId']}")
        try:
            reg_result = single_register_with_retry(reg_info)
            success_count += 1
            print(f"🎉 第{i}个账号注册成功！")
            print(f"  ✔ 用户名：{reg_info['username']}")
            print(f"  ✔ 密码：{reg_info['password']}")
            print(f"  ✔ 设备ID：{reg_info['deviceId']}")
            print(f"  ✔ 用户ID：{reg_result.get('userId')}")
        except Exception as e:
            fail_count += 1
            fail_list.append(f"第{i}个：{reg_info['username']} - {str(e)}")
            print(f"❌ 第{i}个账号注册失败：{str(e)}")
        print("=" * 50 + "\n")

    # 统计报告
    print("===== 批量注册完成 · 统计报告 =====")
    print(f"📊 总尝试：{loop_times}个 | 成功：{success_count}个 | 失败：{fail_count}个")
    if fail_list:
        print("❌ 失败详情：")
        for fail in fail_list:
            print(f"  - {fail}")
    if success_count == loop_times:
        print("🎉 恭喜！所有账号均注册成功！")
