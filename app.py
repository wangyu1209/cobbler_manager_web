"""
Cobbler Web 管理界面 — Flask 主应用
支持运行时动态修改 Cobbler 连接配置
"""

import os
from flask import (Flask, render_template, request,
                   redirect, url_for, flash, jsonify)
from cobbler_client import CobblerClient, CobblerError
from config_manager import load_config, save_config

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cobbler-web-dev-key-change-me")


def get_client():
    """每次请求都从配置文件读取最新的连接信息"""
    config = load_config()
    return CobblerClient(
        config.get("cobbler_url", ""),
        config.get("cobbler_user", ""),
        config.get("cobbler_password", ""),
    )


def _need_setup():
    """检查是否需要首次配置"""
    config = load_config()
    return config.get("cobbler_url", "") == DEFAULT_URL_PLACEHOLDER


DEFAULT_URL_PLACEHOLDER = "http://192.168.1.10/cobbler_api"


# ── 仪表盘 ─────────────────────────────────────────────────────

@app.route("/")
def index():
    if _need_setup():
        flash("请先配置 Cobbler 连接信息", "error")
        return redirect(url_for("settings"))

    client = get_client()
    connected, message = client.test_connection()
    systems = client.get_systems() if connected else []
    profiles = client.get_profiles() if connected else []
    return render_template("index.html",
                           connected=connected,
                           connection_message=message,
                           systems_count=len(systems),
                           profiles_count=len(profiles))


# ── System 列表 ────────────────────────────────────────────────

@app.route("/systems")
def systems():
    client = get_client()
    try:
        all_systems = client.get_systems()
        for s in all_systems:
            s["net_info"] = CobblerClient.extract_network(s)
        return render_template("systems.html", systems=all_systems)
    except CobblerError as e:
        flash(str(e), "error")
        return render_template("systems.html", systems=[])


# ── Profile 列表 ───────────────────────────────────────────────

@app.route("/profiles")
def profiles():
    client = get_client()
    try:
        all_profiles = client.get_profiles()
        return render_template("profiles.html", profiles=all_profiles)
    except CobblerError as e:
        flash(str(e), "error")
        return render_template("profiles.html", profiles=[])


# ── 添加 System ────────────────────────────────────────────────

@app.route("/system/add", methods=["GET", "POST"])
def add_system():
    client = get_client()
    try:
        profiles_list = client.get_profiles()
    except CobblerError:
        profiles_list = []

    if request.method == "POST":
        hostname = request.form.get("hostname", "").strip()
        mac = request.form.get("mac", "").strip()
        ip = request.form.get("ip", "").strip()
        gateway = request.form.get("gateway", "").strip()
        dns_raw = request.form.get("dns", "").strip()
        profile = request.form.get("profile", "").strip()
        netmask = request.form.get("netmask", "255.255.255.0").strip()

        dns_list = [d.strip() for d in dns_raw.split(",") if d.strip()]

        if not all([hostname, mac, ip, gateway, profile]) or not dns_list:
            flash("所有必填字段都不能为空", "error")
            return render_template("add_system.html",
                                   profiles=profiles_list,
                                   form=request.form)

        try:
            message = client.add_system(
                hostname, mac, ip, gateway, dns_list, profile, netmask
            )
            flash(message, "success")
            return redirect(url_for("systems"))
        except CobblerError as e:
            flash(str(e), "error")
            return render_template("add_system.html",
                                   profiles=profiles_list,
                                   form=request.form)

    return render_template("add_system.html",
                           profiles=profiles_list, form={})


# ── 重装 System ────────────────────────────────────────────────

@app.route("/system/<hostname>/reinstall", methods=["GET", "POST"])
def reinstall(hostname):
    client = get_client()

    if request.method == "POST":
        new_hostname = request.form.get("new_hostname", "").strip() or None
        profile = request.form.get("profile", "").strip() or None
        mac = request.form.get("mac", "").strip() or None
        ip = request.form.get("ip", "").strip() or None
        netmask = request.form.get("netmask", "").strip() or None
        gateway = request.form.get("gateway", "").strip() or None
        dns_raw = request.form.get("dns", "").strip()
        dns_list = ([d.strip() for d in dns_raw.split(",") if d.strip()]
                    if dns_raw else None)

        try:
            message = client.reinstall_system(
                hostname, new_hostname=new_hostname, profile=profile,
                mac=mac, ip=ip, netmask=netmask,
                gateway=gateway, dns_list=dns_list,
            )
            flash(message, "success")
            return redirect(url_for("systems"))
        except CobblerError as e:
            flash(str(e), "error")
            return redirect(url_for("reinstall", hostname=hostname))

    try:
        system_data = client.get_system(hostname)
        current = CobblerClient.extract_network(system_data)
        profiles_list = client.get_profiles()
        return render_template("reinstall.html",
                               hostname=hostname,
                               current=current,
                               profiles=profiles_list)
    except CobblerError as e:
        flash(str(e), "error")
        return redirect(url_for("systems"))


# ── 预览 Kickstart ─────────────────────────────────────────────

@app.route("/system/<hostname>/preview")
def preview(hostname):
    client = get_client()
    try:
        system_data = client.get_system(hostname)
        profile = system_data.get("profile", "")
        kickstart = client.preview_kickstart(hostname)
        return render_template("preview.html",
                               hostname=hostname,
                               profile=profile,
                               kickstart=kickstart)
    except CobblerError as e:
        flash(str(e), "error")
        return redirect(url_for("systems"))


# ── 取消重装 ───────────────────────────────────────────────────

@app.route("/system/<hostname>/cancel", methods=["POST"])
def cancel_reinstall(hostname):
    client = get_client()
    try:
        message = client.cancel_reinstall(hostname)
        flash(message, "success")
    except CobblerError as e:
        flash(str(e), "error")
    return redirect(url_for("systems"))


# ── 删除 System ────────────────────────────────────────────────

@app.route("/system/<hostname>/delete", methods=["POST"])
def delete_system(hostname):
    client = get_client()
    try:
        message = client.delete_system(hostname)
        flash(message, "success")
    except CobblerError as e:
        flash(str(e), "error")
    return redirect(url_for("systems"))


# ── 设置页面 ───────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        url = request.form.get("cobbler_url", "").strip()
        user = request.form.get("cobbler_user", "").strip()
        password = request.form.get("cobbler_password", "").strip()

        if not all([url, user, password]):
            flash("所有字段都不能为空", "error")
            return render_template("settings.html", config={
                "cobbler_url": url,
                "cobbler_user": user,
                "cobbler_password": password,
            })

        # 保存配置
        save_config({
            "cobbler_url": url,
            "cobbler_user": user,
            "cobbler_password": password,
        })

        # 保存后立即测试连接
        client = CobblerClient(url, user, password)
        connected, message = client.test_connection()

        if connected:
            flash(f"配置已保存，连接测试通过: {message}", "success")
        else:
            flash(f"配置已保存，但连接测试失败: {message}", "error")

        return redirect(url_for("settings"))

    config = load_config()
    return render_template("settings.html", config=config)


@app.route("/settings/test", methods=["POST"])
def test_connection():
    """AJAX 接口：测试当前配置的连接"""
    config = load_config()
    client = CobblerClient(
        config.get("cobbler_url", ""),
        config.get("cobbler_user", ""),
        config.get("cobbler_password", ""),
    )
    connected, message = client.test_connection()
    return jsonify({"connected": connected, "message": message})


@app.route("/settings/test-new", methods=["POST"])
def test_new_connection():
    """AJAX 接口：测试提交的新配置连接（不保存）"""
    data = request.get_json() or {}
    url = data.get("cobbler_url", "")
    user = data.get("cobbler_user", "")
    password = data.get("cobbler_password", "")

    if not all([url, user, password]):
        return jsonify({"connected": False, "message": "所有字段都不能为空"})

    client = CobblerClient(url, user, password)
    connected, message = client.test_connection()
    return jsonify({"connected": connected, "message": message})


# ── 健康检查 ───────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ── 启动 ───────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

