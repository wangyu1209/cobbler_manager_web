"""
Cobbler Web 管理界面 — Flask 主应用
"""

import os
import subprocess
import concurrent.futures
from flask import (Flask, render_template, request,
                   redirect, url_for, flash, jsonify)
from cobbler_client import CobblerClient, CobblerError
from config_manager import load_config, save_config

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cobbler-web-dev-key-change-me")

DEFAULT_URL_PLACEHOLDER = "http://192.168.1.10/cobbler_api"


def get_client():
    config = load_config()
    return CobblerClient(
        config.get("cobbler_url", ""),
        config.get("cobbler_user", ""),
        config.get("cobbler_password", ""),
    )


def _need_setup():
    config = load_config()
    return config.get("cobbler_url", "") == DEFAULT_URL_PLACEHOLDER


def increment_ip(ip_str, offset):
    parts = list(map(int, ip_str.split(".")))
    parts[3] += offset
    while parts[3] > 255:
        parts[3] -= 256
        parts[2] += 1
    while parts[2] > 255:
        parts[2] -= 256
        parts[1] += 1
    return ".".join(map(str, parts))


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
        # 从 Cobbler 获取所有 profile（而非从 system 去重）
        all_profiles = client.get_profiles()
        profiles_set = sorted([p.get("name", "") for p in all_profiles if p.get("name")])
        return render_template("systems.html",
                               systems=all_systems,
                               profile_list=profiles_set)
    except CobblerError as e:
        flash(str(e), "error")
        return render_template("systems.html", systems=[], profile_list=[])


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


# ── Kickstart 模板 ─────────────────────────────────────────────

@app.route("/kickstart-templates")
def kickstart_templates():
    client = get_client()
    try:
        all_profiles = client.get_profiles()
        templates = []
        for p in all_profiles:
            templates.append({
                "profile": p.get("name", ""),
                "distro": p.get("distro", ""),
                "kickstart_path": p.get("kickstart", ""),
            })
        return render_template("kickstart_templates.html",
                               templates=templates)
    except CobblerError as e:
        flash(str(e), "error")
        return render_template("kickstart_templates.html", templates=[])


@app.route("/kickstart-templates/<profile_name>")
def kickstart_template_detail(profile_name):
    client = get_client()
    try:
        profiles_list = client.get_profiles()
        profile_data = None
        for p in profiles_list:
            if p.get("name") == profile_name:
                profile_data = p
                break

        if not profile_data:
            flash(f"profile '{profile_name}' 不存在", "error")
            return redirect(url_for("kickstart_templates"))

        kickstart_content = client.get_kickstart_template(profile_name)
        kickstart_path = profile_data.get("kickstart", "")

        return render_template("kickstart_template_detail.html",
                               profile_name=profile_name,
                               profile_data=profile_data,
                               kickstart_path=kickstart_path,
                               kickstart_content=kickstart_content)
    except CobblerError as e:
        flash(str(e), "error")
        return redirect(url_for("kickstart_templates"))


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


# ── 批量重装 ───────────────────────────────────────────────────

@app.route("/system/batch-reinstall", methods=["POST"])
def batch_reinstall():
    selected = request.form.get("selected_hosts", "")
    hostnames = [h.strip() for h in selected.split(",") if h.strip()]

    if not hostnames:
        flash("没有选中任何设备", "error")
        return redirect(url_for("systems"))

    profile = request.form.get("profile", "").strip() or None
    ip_start = request.form.get("ip_start", "").strip() or None
    netmask = request.form.get("netmask", "").strip() or None
    gateway = request.form.get("gateway", "").strip() or None
    dns_raw = request.form.get("dns", "").strip()
    dns_list = ([d.strip() for d in dns_raw.split(",") if d.strip()]
                if dns_raw else None)

    client = get_client()
    conn = client._get_conn()
    token = client._get_token()

    results = []
    success_count = 0
    fail_count = 0

    for idx, hostname in enumerate(hostnames):
        try:
            current_ip = increment_ip(ip_start, idx) if ip_start else None

            systems_list = conn.get_systems()
            if hostname not in [s.get("name") for s in systems_list]:
                results.append({"hostname": hostname, "status": "error",
                                "message": "system 不存在"})
                fail_count += 1
                continue

            handle = conn.get_system_handle(hostname, token)

            if profile:
                conn.modify_system(handle, "profile", profile, token)
            if current_ip:
                conn.modify_system(handle, "ipaddress-eth0", current_ip, token)
                conn.modify_system(handle, "static-eth0", True, token)
            if netmask:
                conn.modify_system(handle, "netmask-eth0", netmask, token)
            if gateway:
                conn.modify_system(handle, "gateway", gateway, token)
            if dns_list:
                conn.modify_system(handle, "name_servers", dns_list, token)

            conn.modify_system(handle, "netboot_enabled", 1, token)

            if idx < len(hostnames) - 1:
                conn.save_system(handle, token)
            else:
                conn.save_system(handle, token)
                conn.sync(token)

            msg = "已标记重装"
            if current_ip:
                msg += f" (IP: {current_ip})"
            results.append({"hostname": hostname, "status": "success",
                            "message": msg})
            success_count += 1

        except Exception as e:
            results.append({"hostname": hostname, "status": "error",
                            "message": str(e)})
            fail_count += 1

    flash(f"批量重装完成: 成功 {success_count}, 失败 {fail_count}", "success")
    return render_template("batch_result.html",
                           results=results,
                           title="批量重装结果",
                           action="重装")


# ── 批量取消重装标记 ───────────────────────────────────────────

@app.route("/system/batch-cancel", methods=["POST"])
def batch_cancel():
    selected = request.form.get("selected_hosts", "")
    hostnames = [h.strip() for h in selected.split(",") if h.strip()]

    if not hostnames:
        flash("没有选中任何设备", "error")
        return redirect(url_for("systems"))

    client = get_client()
    conn = client._get_conn()
    token = client._get_token()

    results = []
    success_count = 0
    fail_count = 0

    for idx, hostname in enumerate(hostnames):
        try:
            systems_list = conn.get_systems()
            if hostname not in [s.get("name") for s in systems_list]:
                results.append({"hostname": hostname, "status": "error",
                                "message": "system 不存在"})
                fail_count += 1
                continue

            handle = conn.get_system_handle(hostname, token)
            conn.modify_system(handle, "netboot_enabled", 0, token)

            if idx < len(hostnames) - 1:
                conn.save_system(handle, token)
            else:
                conn.save_system(handle, token)
                conn.sync(token)

            results.append({"hostname": hostname, "status": "success",
                            "message": "已取消重装标记"})
            success_count += 1

        except Exception as e:
            results.append({"hostname": hostname, "status": "error",
                            "message": str(e)})
            fail_count += 1

    flash(f"批量取消完成: 成功 {success_count}, 失败 {fail_count}", "success")
    return render_template("batch_result.html",
                           results=results,
                           title="批量取消结果",
                           action="取消重装")


# ── IPMI 管理 ──────────────────────────────────────────────────

@app.route("/ipmi", methods=["GET", "POST"])
def ipmi():
    if request.method == "POST":
        default_user = request.form.get("default_user", "root").strip()
        default_password = request.form.get("default_password", "").strip()
        action = request.form.get("action", "")
        device_list_raw = request.form.get("device_list", "").strip()

        if not device_list_raw:
            flash("设备列表不能为空", "error")
            return render_template("ipmi.html", results=None)

        if not default_password:
            flash("统一凭据密码不能为空", "error")
            return render_template("ipmi.html", results=None)

        # 解析设备列表
        devices = []
        for line in device_list_raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            bmc_ip = parts[0]
            user = parts[1] if len(parts) > 1 else default_user
            password = parts[2] if len(parts) > 2 else default_password
            devices.append({"ip": bmc_ip, "user": user, "password": password})

        if not devices:
            flash("设备列表为空", "error")
            return render_template("ipmi.html", results=None)

        # IPMI 操作映射（每个操作对应一组顺序执行的命令）
        action_map = {
            "status": [
                ["chassis", "power", "status"],
            ],
            "pxe": [
                ["chassis", "bootdev", "pxe", "options=persistent"],
                ["chassis", "bootparam", "set", "bootflag", "force_pxe"],
                ["power", "cycle"],
                ["power", "on"],
            ],
            "cdrom": [
                ["chassis", "bootdev", "cdrom"],
                ["power", "cycle"],
                ["power", "on"],
            ],
            "bios": [
                ["chassis", "bootdev", "bios"],
                ["power", "cycle"],
                ["power", "on"],
            ],
            "reboot": [
                ["power", "cycle"],
            ],
            "poweron": [
                ["power", "on"],
            ],
            "poweroff": [
                ["power", "off"],
            ],
        }

        action_labels = {
            "status":   "电源状态",
            "pxe":      "PXE 启动",
            "cdrom":    "光驱启动",
            "bios":     "进入 BIOS",
            "reboot":   "重启",
            "poweron":  "开机",
            "poweroff": "关机",
        }

        if action not in action_map:
            flash("未知操作", "error")
            return render_template("ipmi.html", results=None)

        cmd_list = action_map[action]
        action_label = action_labels[action]

        def run_ipmi(device):
            bmc_ip = device["ip"]
            user = device["user"]
            password = device["password"]

            base_cmd = ["ipmitool", "-I", "lanplus",
                        "-H", bmc_ip, "-U", user, "-P", password]

            try:
                outputs = []
                for idx, args in enumerate(cmd_list):
                    cmd = base_cmd + args
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=20
                    )
                    output = result.stdout.strip()
                    err = result.stderr.strip()

                    if result.returncode != 0:
                        err_msg = err or output
                        cmd_desc = " ".join(args)
                        return {
                            "ip": bmc_ip,
                            "status": "error",
                            "message": f"第{idx+1}步失败({cmd_desc}): {err_msg}"
                        }

                    if output:
                        outputs.append(output)

                if action == "status":
                    return {"ip": bmc_ip, "status": "success",
                            "message": outputs[0] if outputs else "执行成功"}
                else:
                    return {"ip": bmc_ip, "status": "success",
                            "message": f"{action_label}成功"}

            except subprocess.TimeoutExpired:
                return {"ip": bmc_ip, "status": "error",
                        "message": "IPMI 连接超时（20秒）"}
            except FileNotFoundError:
                return {"ip": bmc_ip, "status": "error",
                        "message": "容器内未安装 ipmitool"}
            except Exception as e:
                return {"ip": bmc_ip, "status": "error", "message": str(e)}

        # 并发执行
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(run_ipmi, d): d for d in devices}
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda x: x["ip"])

        success_count = sum(1 for r in results if r["status"] == "success")
        fail_count = len(results) - success_count
        flash(f"IPMI {action_label} 完成: 成功 {success_count}, 失败 {fail_count}", "success")

        return render_template("ipmi.html", results=results)

    return render_template("ipmi.html", results=None)


# ── 设置 ───────────────────────────────────────────────────────

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

        save_config({
            "cobbler_url": url,
            "cobbler_user": user,
            "cobbler_password": password,
        })

        client = CobblerClient(url, user, password)
        connected, message = client.test_connection()

        if connected:
            flash("配置已保存，连接测试通过", "success")
        else:
            flash(f"配置已保存，但连接测试失败: {message}", "error")

        return redirect(url_for("settings"))

    config = load_config()
    return render_template("settings.html", config=config)


@app.route("/settings/test", methods=["POST"])
def test_connection():
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

