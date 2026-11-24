"""Minimal HID access layer built on ctypes (no third-party packages).

Provides:
    enumerate_devices()  -> list[HidInfo]   every present HID collection
    HidDevice.open()     -> opened handle with write/read helpers

Only the pieces needed by the battery providers are implemented, but the
abstraction is general enough for normal HID feature/input reports.
"""

from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from dataclasses import dataclass, field

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
cfgmgr32 = ctypes.WinDLL("cfgmgr32", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
ERROR_IO_PENDING = 997
ERROR_NO_MORE_ITEMS = 259
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
FILE_FLAG_OVERLAPPED = 0x40000000


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, text: str):
        super().__init__()
        self.from_text(text)

    def from_text(self, text: str) -> None:
        tail = text.strip().strip("{}")
        parts = tail.split("-")
        self.Data1 = int(parts[0], 16)
        self.Data2 = int(parts[1], 16)
        self.Data3 = int(parts[2], 16)
        rest = bytes.fromhex(parts[3] + parts[4])
        for i, b in enumerate(rest):
            self.Data4[i] = b


HID_GUID = GUID("{4D1E55B2-F16F-11CF-88CB-001111000030}")


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(wintypes.ULONG)),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


# --- prototypes -----------------------------------------------------------
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID),
    wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL

cfgmgr32.CM_Locate_DevNodeW.argtypes = [
    ctypes.POINTER(wintypes.DWORD), wintypes.LPCWSTR, wintypes.ULONG]
cfgmgr32.CM_Locate_DevNodeW.restype = wintypes.ULONG
cfgmgr32.CM_Get_Parent.argtypes = [
    ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG]
cfgmgr32.CM_Get_Parent.restype = wintypes.ULONG
cfgmgr32.CM_Get_Device_IDW.argtypes = [
    wintypes.DWORD, wintypes.LPWSTR, wintypes.ULONG, wintypes.ULONG]
cfgmgr32.CM_Get_Device_IDW.restype = wintypes.ULONG

hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = wintypes.BOOL
hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = wintypes.BOOL
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_FreePreparsedData.restype = wintypes.BOOL
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = ctypes.c_long
hid.HidD_GetProductString.argtypes = [wintypes.HANDLE, ctypes.c_wchar_p, wintypes.ULONG]
hid.HidD_GetProductString.restype = wintypes.BOOL
hid.HidD_GetManufacturerString.argtypes = [wintypes.HANDLE, ctypes.c_wchar_p, wintypes.ULONG]
hid.HidD_GetManufacturerString.restype = wintypes.BOOL
hid.HidD_GetSerialNumberString.argtypes = [wintypes.HANDLE, ctypes.c_wchar_p, wintypes.ULONG]
hid.HidD_GetSerialNumberString.restype = wintypes.BOOL
hid.HidD_SetNumInputBuffers.argtypes = [wintypes.HANDLE, wintypes.ULONG]
hid.HidD_SetNumInputBuffers.restype = wintypes.BOOL
hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_GetFeature.restype = wintypes.BOOL
hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_SetFeature.restype = wintypes.BOOL

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreateEventW.argtypes = [
    ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
kernel32.ResetEvent.restype = wintypes.BOOL
kernel32.GetOverlappedResult.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
    ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
kernel32.GetOverlappedResult.restype = wintypes.BOOL
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.CancelIoEx.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.ReadFile.restype = wintypes.BOOL


def _wstring_call(fn, handle, size: int = 512) -> str:
    buf = ctypes.create_unicode_buffer(size)
    try:
        if fn(handle, buf, size * 2):
            return buf.value
    except Exception:
        pass
    return ""


@dataclass
class HidInfo:
    path: str
    vendor_id: int = 0
    product_id: int = 0
    version: int = 0
    product: str = ""
    manufacturer: str = ""
    serial: str = ""
    usage_page: int = 0
    usage: int = 0
    input_len: int = 0
    output_len: int = 0
    feature_len: int = 0
    instance_id: str = ""
    ancestors: list[str] = field(default_factory=list)

    @property
    def vid_pid(self) -> str:
        return f"{self.vendor_id:04X}:{self.product_id:04X}"

    @property
    def is_bluetooth(self) -> bool:
        if self.ancestors:
            return any(a.upper().startswith(("BTHENUM", "BTHLE"))
                       for a in self.ancestors)
        p = self.path.upper()
        return "BTHENUM" in p or "BTHLE" in p

    @property
    def is_usb(self) -> bool:
        if self.ancestors:
            return any(a.upper().startswith("USB\\") or
                       a.upper().startswith("USB#") for a in self.ancestors)
        return "USB#" in self.path.upper()

    @property
    def is_logitech(self) -> bool:
        return self.vendor_id == 0x046D

    @property
    def hw_node(self) -> str:
        """Identifier of the physical device behind this collection.

        Several HID collections (keyboard + consumer control + vendor page)
        belong to one device; this folds them together.
        """
        for ancestor in self.ancestors:
            upper = ancestor.upper()
            if upper.startswith("BTHENUM") and "DEV_" in upper:
                return ancestor
            if upper.startswith("USB\\") and "&MI_" not in upper:
                return ancestor
        base = self.instance_id.rsplit("\\", 1)[0]
        return base.split("&COL")[0].rstrip("&")

    @property
    def is_receiver(self) -> bool:
        """USB dongle that hosts one or more wireless devices."""
        text = f"{self.product} {self.manufacturer}".lower()
        return any(w in text for w in
                   ("receiver", "dongle", "接收器", "usb receiver"))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"HidInfo({self.vid_pid} page=0x{self.usage_page:04X} "
                f"usage=0x{self.usage:04X} out={self.output_len} "
                f"in={self.input_len} feat={self.feature_len} "
                f"name={self.product!r} bt={self.is_bluetooth})")


def _instance_from_path(path: str) -> str:
    """Turn a HID interface path into its device instance id.

    ``\\\\?\\hid#vid_046d&pid_c539&mi_02&col01#8&2325ecc1&0&0000#{guid}``
    becomes ``HID\\VID_046D&PID_C539&MI_02&COL01\\8&2325ECC1&0&0000``.
    """
    text = path
    if text.startswith("\\\\?\\"):
        text = text[4:]
    if "#{" in text:
        text = text.rsplit("#", 1)[0]
    parts = [p for p in text.split("#") if p]
    if len(parts) < 2:
        return ""
    return "\\".join([parts[0].upper()] + [p.upper() for p in parts[1:]])


def _device_ancestors(instance_id: str, limit: int = 8) -> list[str]:
    """Walk up the device tree collecting ancestor instance ids."""
    chain: list[str] = []
    if not instance_id:
        return chain
    node = wintypes.DWORD(0)
    if cfgmgr32.CM_Locate_DevNodeW(ctypes.byref(node), instance_id, 0) != 0:
        return chain
    for _ in range(limit):
        parent = wintypes.DWORD(0)
        if cfgmgr32.CM_Get_Parent(ctypes.byref(parent), node.value, 0) != 0:
            break
        node = parent
        buf = ctypes.create_unicode_buffer(512)
        if cfgmgr32.CM_Get_Device_IDW(node.value, buf, 512, 0) != 0:
            break
        chain.append(buf.value)
    return chain


def _open_raw(path: str, write: bool = True) -> int:
    access = GENERIC_READ | (GENERIC_WRITE if write else 0)
    # Overlapped mode is required for the timed reads/writes in HidDevice;
    # without FILE_FLAG_OVERLAPPED a blocking ReadFile would never time out.
    handle = kernel32.CreateFileW(
        path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
        OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
    if handle == INVALID_HANDLE_VALUE or not handle:
        return 0
    return handle


def _describe(path: str, handle: int) -> HidInfo:
    info = HidInfo(path=path)
    attrs = HIDD_ATTRIBUTES()
    attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
    if hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
        info.vendor_id = attrs.VendorID
        info.product_id = attrs.ProductID
        info.version = attrs.VersionNumber
    info.product = _wstring_call(hid.HidD_GetProductString, handle)
    info.manufacturer = _wstring_call(hid.HidD_GetManufacturerString, handle)
    info.serial = _wstring_call(hid.HidD_GetSerialNumberString, handle)

    preparsed = ctypes.c_void_p()
    if hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(preparsed, ctypes.byref(caps)) >= 0:
            info.usage_page = caps.UsagePage
            info.usage = caps.Usage
            info.input_len = caps.InputReportByteLength
            info.output_len = caps.OutputReportByteLength
            info.feature_len = caps.FeatureReportByteLength
        hid.HidD_FreePreparsedData(preparsed)
    return info


def enumerate_devices() -> list[HidInfo]:
    """Return every HID collection currently present on the system."""
    result: list[HidInfo] = []
    dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(HID_GUID), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if dev_info == INVALID_HANDLE_VALUE:
        return result
    try:
        index = 0
        while True:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                    dev_info, None, ctypes.byref(HID_GUID), index,
                    ctypes.byref(iface)):
                break
            index += 1
            required = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(iface), None, 0,
                ctypes.byref(required), None)
            if not required.value:
                continue
            buf = ctypes.create_string_buffer(required.value + 16)
            detail = ctypes.cast(
                buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
            detail.contents.cbSize = ctypes.sizeof(
                SP_DEVICE_INTERFACE_DETAIL_DATA_W)
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info, ctypes.byref(iface), ctypes.byref(buf),
                    required, ctypes.byref(required), None):
                continue
            # ``DevicePath`` is an open WCHAR array of length 1 in the struct
            # definition, so read it through the raw buffer instead.
            path = ctypes.wstring_at(
                ctypes.addressof(buf)
                + SP_DEVICE_INTERFACE_DETAIL_DATA_W.DevicePath.offset)
            if not path:
                continue
            handle = _open_raw(path, write=False)
            if not handle:
                continue
            try:
                instance = _instance_from_path(path)
                info = _describe(path, handle)
                info.instance_id = instance
                info.ancestors = _device_ancestors(instance)
                result.append(info)
            finally:
                kernel32.CloseHandle(handle)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return result


class HidDevice:
    """An opened HID collection supporting overlapped read/write."""

    def __init__(self, info: HidInfo, writable: bool = True):
        self.info = info
        self._handle = _open_raw(info.path, write=writable)
        if not self._handle:
            raise OSError(f"cannot open HID device {info.vid_pid}: {info.path}")
        self._event = kernel32.CreateEventW(None, True, False, None)
        self._ov = OVERLAPPED()
        self._ov.hEvent = self._event
        try:
            hid.HidD_SetNumInputBuffers(self._handle, 64)
        except Exception:
            pass

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = 0
        if self._event:
            kernel32.CloseHandle(self._event)
            self._event = 0

    def __enter__(self) -> "HidDevice":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- I/O --------------------------------------------------------------
    def write(self, data: bytes, timeout_ms: int = 150) -> bool:
        if not self._handle:
            return False
        written = wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        kernel32.ResetEvent(self._event)
        ok = kernel32.WriteFile(self._handle, buf, len(data),
                                ctypes.byref(written), ctypes.byref(self._ov))
        if not ok:
            if ctypes.get_last_error() != ERROR_IO_PENDING:
                return False
            rc = kernel32.WaitForSingleObject(self._event, timeout_ms)
            if rc != WAIT_OBJECT_0:
                kernel32.CancelIoEx(self._handle, ctypes.byref(self._ov))
                return False
            if not kernel32.GetOverlappedResult(
                    self._handle, ctypes.byref(self._ov),
                    ctypes.byref(written), False):
                return False
        return written.value > 0

    def read(self, length: int, timeout_ms: int = 150) -> bytes | None:
        if not self._handle:
            return None
        read = wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(length)
        self._ov.Internal = 0
        self._ov.InternalHigh = 0
        kernel32.ResetEvent(self._event)
        ok = kernel32.ReadFile(self._handle, buf, length,
                               ctypes.byref(read), ctypes.byref(self._ov))
        if not ok:
            if ctypes.get_last_error() != ERROR_IO_PENDING:
                return None
            rc = kernel32.WaitForSingleObject(self._event, timeout_ms)
            if rc != WAIT_OBJECT_0:
                self._cancel_pending()
                return None
            if not kernel32.GetOverlappedResult(
                    self._handle, ctypes.byref(self._ov),
                    ctypes.byref(read), False):
                return None
        if not read.value:
            return None
        return buf.raw[:read.value]

    def _cancel_pending(self) -> None:
        """Cancel an outstanding overlapped op and make sure it completed."""
        kernel32.CancelIoEx(self._handle, ctypes.byref(self._ov))
        kernel32.WaitForSingleObject(self._event, 1000)
        done = wintypes.DWORD(0)
        kernel32.GetOverlappedResult(self._handle, ctypes.byref(self._ov),
                                     ctypes.byref(done), True)

    def get_feature(self, report_id: int, length: int) -> bytes | None:
        buf = ctypes.create_string_buffer(length)
        buf.raw = bytes([report_id]) + bytes(length - 1)
        if not hid.HidD_GetFeature(self._handle, buf, length):
            return None
        return buf.raw[:length]

    def set_feature(self, data: bytes) -> bool:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        return bool(hid.HidD_SetFeature(self._handle, buf, len(data)))


# Convenience helpers -------------------------------------------------------
def find_devices(predicate) -> list[HidInfo]:
    return [d for d in enumerate_devices() if predicate(d)]


def parse_vid_pid_from_path(path: str) -> tuple[int, int]:
    upper = path.upper()
    vid = pid = 0
    for token in upper.split("#"):
        if token.startswith("VID_"):
            try:
                vid = int(token[4:8], 16)
            except ValueError:
                pass
        elif token.startswith("PID_"):
            try:
                pid = int(token[4:8], 16)
            except ValueError:
                pass
    return vid, pid


def _selftest() -> None:  # pragma: no cover - manual probe
    devices = enumerate_devices()
    print(f"{len(devices)} HID collections")
    for d in devices:
        print(d)


if __name__ == "__main__":  # pragma: no cover
    _selftest()
