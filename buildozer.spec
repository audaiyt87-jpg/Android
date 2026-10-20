[app]

# اسم التطبيق كما يظهر على الهاتف
title = Gold Portfolio

# اسم الحزمة والنطاق
package.name = goldportfolio
package.domain = com.rajhi.gold

# مجلد المصدر
source.dir = .
source.include_exts = py,png,jpg,ttf,json

# رقم الإصدار
version = 1.0

# المتطلبات (نسخ متوافقة مع Python 3.11)
requirements = python3,kivy==2.3.0,openssl,arabic_reshaper,python-bidi==0.4.2

# الاتجاه
orientation = portrait

# ===== إعدادات الأندرويد (تحت [app] مباشرة - مهم) =====
android.permissions = INTERNET
android.api = 34
android.minapi = 24
android.ndk_api = 24

# تثبيت نسخة NDK مستقرة ومجرّبة
android.ndk = 25b

# المعماريات
android.archs = arm64-v8a, armeabi-v7a

# قبول تراخيص SDK تلقائياً
android.accept_sdk_license = True

# === الإصلاح الجوهري: تثبيت python-for-android على إصدار مستقر ===
# هذا الإصدار يبني Python 3.11 (المتوافق مع Kivy 2.3.0) بدل Python 3.14
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
