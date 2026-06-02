"""
Cobbler XML-RPC API 客户端封装
"""

import xmlrpc.client as xc


class CobblerError(Exception):
    """Cobbler 操作异常"""
    pass


class CobblerClient:

    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password
        self._conn = None
        self._token = None

    # ── 连接与认证 ──────────────────────────────────────────────

    def _get_conn(self):
        if self._conn is None:
            self._conn = xc.ServerProxy(self.url, allow_none=True)
        return self._conn

    def _get_token(self):
        conn = self._get_conn()
        if self._token is None:
            try:
                self._token = conn.login(self.username, self.password)
            except Exception as e:
                raise CobblerError(f"认证失败: {e}")
        return self._token

    def test_connection(self):
        """测试 Cobbler 连接是否正常"""
        try:
            conn = self._get_conn()
            distros = conn.get_distros()
            return True, f"连接成功，共 {len(distros)} 个 distro"
        except Exception as e:
            return False, f"连接失败: {e}"

    # ── 查询操作（不需要认证）──────────────────────────────────

    def get_systems(self):
        """获取所有 system 列表"""
        try:
            return self._get_conn().get_systems()
        except Exception as e:
            raise CobblerError(f"获取 system 列表失败: {e}")

    def get_profiles(self):
        """获取所有 profile 列表"""
        try:
            return self._get_conn().get_profiles()
        except Exception as e:
            raise CobblerError(f"获取 profile 列表失败: {e}")

    def get_system(self, hostname):
        """获取单个 system 详情"""
        try:
            return self._get_conn().get_system(hostname)
        except Exception as e:
            raise CobblerError(f"获取 system '{hostname}' 失败: {e}")

    def preview_kickstart(self, hostname):
        """预览 system 的 kickstart 内容"""
        conn = self._get_conn()
        systems = conn.get_systems()
        if hostname not in [s.get("name") for s in systems]:
            raise CobblerError(f"system '{hostname}' 不存在")

        system_info = conn.get_system(hostname)
        profile = system_info.get("profile", "")

        if not profile:
            raise CobblerError(f"system '{hostname}' 没有关联的 profile")

        try:
            return conn.generate_kickstart(profile)
        except xc.Fault as e:
            raise CobblerError(f"生成 kickstart 失败: {e}")

    # ── 写入操作（需要认证）────────────────────────────────────

    def add_system(self, hostname, mac, ip, gateway, dns_list,
                   profile, netmask="255.255.255.0"):
        """新增 system"""
        token = self._get_token()
        conn = self._get_conn()

        # 检查 system 是否已存在
        systems = conn.get_systems()
        if hostname in [s.get("name") for s in systems]:
            raise CobblerError(f"system '{hostname}' 已存在")

        # 检查 profile 是否存在
        profiles = conn.get_profiles()
        if profile not in [p.get("name") for p in profiles]:
            raise CobblerError(f"profile '{profile}' 不存在")

        handle = conn.new_system(token)
        conn.modify_system(handle, "name", hostname, token)
        conn.modify_system(handle, "hostname", hostname, token)
        conn.modify_system(handle, "macaddress-eth0", mac, token)
        conn.modify_system(handle, "ipaddress-eth0", ip, token)
        conn.modify_system(handle, "netmask-eth0", netmask, token)
        conn.modify_system(handle, "static-eth0", True, token)
        conn.modify_system(handle, "gateway", gateway, token)
        conn.modify_system(handle, "name_servers", dns_list, token)
        conn.modify_system(handle, "profile", profile, token)
        conn.save_system(handle, token)
        conn.sync(token)

        return f"系统 '{hostname}' 已添加并同步完成"

    def delete_system(self, hostname):
        """删除 system"""
        token = self._get_token()
        conn = self._get_conn()

        systems = conn.get_systems()
        if hostname not in [s.get("name") for s in systems]:
            raise CobblerError(f"system '{hostname}' 不存在")

        conn.remove_system(hostname, token)
        conn.sync(token)
        return f"系统 '{hostname}' 已删除"

    def reinstall_system(self, hostname, new_hostname=None, profile=None,
                         mac=None, ip=None, netmask=None,
                         gateway=None, dns_list=None):
        """修改已有 system 属性并标记重装"""
        token = self._get_token()
        conn = self._get_conn()

        systems = conn.get_systems()
        if hostname not in [s.get("name") for s in systems]:
            raise CobblerError(f"system '{hostname}' 不存在")

        handle = conn.get_system_handle(hostname, token)

        # 按需修改各属性
        if profile is not None and profile != "":
            profiles_list = conn.get_profiles()
            if profile not in [p.get("name") for p in profiles_list]:
                raise CobblerError(f"profile '{profile}' 不存在")
            conn.modify_system(handle, "profile", profile, token)

        if new_hostname is not None and new_hostname != "":
            conn.modify_system(handle, "hostname", new_hostname, token)

        if mac is not None and mac != "":
            conn.modify_system(handle, "macaddress-eth0", mac, token)

        if ip is not None and ip != "":
            conn.modify_system(handle, "ipaddress-eth0", ip, token)
            conn.modify_system(handle, "static-eth0", True, token)

        if netmask is not None and netmask != "":
            conn.modify_system(handle, "netmask-eth0", netmask, token)

        if gateway is not None and gateway != "":
            conn.modify_system(handle, "gateway", gateway, token)

        if dns_list is not None:
            conn.modify_system(handle, "name_servers", dns_list, token)

        # 开启 PXE 引导
        conn.modify_system(handle, "netboot_enabled", 1, token)
        conn.save_system(handle, token)
        conn.sync(token)

        return f"系统 '{hostname}' 已修改并标记为重装"

    def cancel_reinstall(self, hostname):
        """取消重装标记"""
        token = self._get_token()
        conn = self._get_conn()

        systems = conn.get_systems()
        if hostname not in [s.get("name") for s in systems]:
            raise CobblerError(f"system '{hostname}' 不存在")

        handle = conn.get_system_handle(hostname, token)
        conn.modify_system(handle, "netboot_enabled", 0, token)
        conn.save_system(handle, token)
        conn.sync(token)

        return f"系统 '{hostname}' 重装标记已取消"

    # ── 辅助方法 ────────────────────────────────────────────────

    @staticmethod
    def extract_network(system_data):
        """从 system 数据中提取网络信息"""
        interfaces = system_data.get("interfaces", {})
        intf_data = {}
        for name, data in interfaces.items():
            intf_data = data
            break

        return {
            "hostname": system_data.get("hostname", ""),
            "profile": system_data.get("profile", ""),
            "ip": intf_data.get("ip_address", ""),
            "mac": intf_data.get("mac_address", ""),
            "netmask": intf_data.get("netmask", "255.255.255.0"),
            "gateway": system_data.get("gateway", ""),
            "dns": ", ".join(system_data.get("name_servers", [])),
            "netboot_enabled": system_data.get("netboot_enabled", 0),
        }
