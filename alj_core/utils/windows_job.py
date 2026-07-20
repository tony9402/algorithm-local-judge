"""Windows Job Object based process-tree isolation.

The module is importable on every platform, but it only loads ``kernel32`` when
``create_windows_job`` is called on Windows.  This keeps Linux and macOS
packaging free from platform-specific import failures.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from typing import Any

JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT = 9
JOB_OBJECT_MSG_JOB_MEMORY_LIMIT = 10
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
JOB_OBJECT_ASSOCIATE_COMPLETION_PORT_INFORMATION_CLASS = 7
WAIT_TIMEOUT = 258
CREATE_SUSPENDED = 0x00000004
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_COMPLETION_MESSAGES = 4096

_MEMORY_FAILURE_EXIT_CODES = {
    0xC0000017,  # STATUS_NO_MEMORY
    0xC000009A,  # STATUS_INSUFFICIENT_RESOURCES
    0xC000012D,  # STATUS_COMMITMENT_LIMIT
}


class WindowsJobError(OSError):
    """Raised when the required Windows isolation boundary cannot be created."""


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _JobObjectAssociateCompletionPort(ctypes.Structure):
    _fields_ = [
        ("CompletionKey", ctypes.c_void_p),
        ("CompletionPort", wintypes.HANDLE),
    ]


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def _last_error(action: str) -> WindowsJobError:
    error = ctypes.get_last_error()
    return WindowsJobError(error, f"Windows process isolation failed: {action}")


class WindowsJob:
    """Own a non-breakaway Job Object for one submitted process tree."""

    creation_flags = CREATE_SUSPENDED

    def __init__(self, memory_limit_bytes: int | None) -> None:
        if os.name != "nt":
            raise WindowsJobError("Windows Job Objects are unavailable on this platform")
        self.memory_limit_bytes = memory_limit_bytes
        self._closed = False
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_signatures()
        self._job = self._kernel32.CreateJobObjectW(None, None)
        if not self._job:
            raise _last_error("CreateJobObjectW")
        self._completion_port = None
        if memory_limit_bytes is not None:
            self._completion_port = self._kernel32.CreateIoCompletionPort(
                INVALID_HANDLE_VALUE,
                None,
                0,
                1,
            )
            if not self._completion_port:
                error = _last_error("CreateIoCompletionPort")
                self.close()
                raise error
        try:
            self._set_limits()
            if self._completion_port is not None:
                self._associate_completion_port()
        except OSError:
            self.close()
            raise

    def _configure_signatures(self) -> None:
        kernel32 = self._kernel32
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateIoCompletionPort.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.c_size_t,
            wintypes.DWORD,
        ]
        kernel32.CreateIoCompletionPort.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.GetQueuedCompletionStatus.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.DWORD,
        ]
        kernel32.GetQueuedCompletionStatus.restype = wintypes.BOOL
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Thread32First.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ThreadEntry32),
        ]
        kernel32.Thread32First.restype = wintypes.BOOL
        kernel32.Thread32Next.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ThreadEntry32),
        ]
        kernel32.Thread32Next.restype = wintypes.BOOL
        kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

    def _set_limits(self) -> None:
        information = _JobObjectExtendedLimitInformation()
        flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if self.memory_limit_bytes is not None:
            if self.memory_limit_bytes <= 0:
                raise WindowsJobError("Windows Job Object memory limit must be positive")
            flags |= JOB_OBJECT_LIMIT_JOB_MEMORY
            information.JobMemoryLimit = self.memory_limit_bytes
        information.BasicLimitInformation.LimitFlags = flags
        if not self._kernel32.SetInformationJobObject(
            self._job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise _last_error("SetInformationJobObject(limits)")

    def _associate_completion_port(self) -> None:
        association = _JobObjectAssociateCompletionPort(
            CompletionKey=self._job,
            CompletionPort=self._completion_port,
        )
        if not self._kernel32.SetInformationJobObject(
            self._job,
            JOB_OBJECT_ASSOCIATE_COMPLETION_PORT_INFORMATION_CLASS,
            ctypes.byref(association),
            ctypes.sizeof(association),
        ):
            raise _last_error("SetInformationJobObject(completion port)")

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        """Attach the process before any result is accepted from it."""
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise WindowsJobError("Windows process handle is unavailable")
        if not self._kernel32.AssignProcessToJobObject(self._job, int(process_handle)):
            raise _last_error("AssignProcessToJobObject")

    def resume(self, process_id: int) -> None:
        """Resume the initial thread only after the suspended process is isolated."""
        snapshot = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == INVALID_HANDLE_VALUE:
            raise _last_error("CreateToolhelp32Snapshot")
        thread_handle = None
        try:
            entry = _ThreadEntry32()
            entry.dwSize = ctypes.sizeof(entry)
            if not self._kernel32.Thread32First(snapshot, ctypes.byref(entry)):
                raise _last_error("Thread32First")
            while True:
                if entry.th32OwnerProcessID == process_id:
                    thread_handle = self._kernel32.OpenThread(
                        THREAD_SUSPEND_RESUME,
                        False,
                        entry.th32ThreadID,
                    )
                    if not thread_handle:
                        raise _last_error("OpenThread")
                    break
                if not self._kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                    break
            if thread_handle is None:
                raise WindowsJobError("Windows process primary thread was not found")
            if self._kernel32.ResumeThread(thread_handle) == 0xFFFFFFFF:
                raise _last_error("ResumeThread")
        finally:
            if thread_handle:
                self._kernel32.CloseHandle(thread_handle)
            self._kernel32.CloseHandle(snapshot)

    def terminate(self) -> None:
        """Terminate every process in the job, including descendants."""
        if self._closed:
            return
        if not self._kernel32.TerminateJobObject(self._job, 1):
            raise _last_error("TerminateJobObject")

    def peak_memory_bytes(self) -> int | None:
        """Return the aggregate peak committed memory for the process tree."""
        if self._closed:
            return None
        information = _JobObjectExtendedLimitInformation()
        if not self._kernel32.QueryInformationJobObject(
            self._job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
            None,
        ):
            raise _last_error("QueryInformationJobObject")
        return int(information.PeakJobMemoryUsed) or None

    def memory_limit_exceeded(self, returncode: int, peak_memory_bytes: int | None) -> bool:
        """Determine whether the configured job-wide memory cap was hit."""
        if self.memory_limit_bytes is None:
            return False
        if self._drain_memory_limit_messages():
            return True
        normalized_returncode = returncode & 0xFFFFFFFF
        if normalized_returncode in _MEMORY_FAILURE_EXIT_CODES:
            return True
        return bool(
            returncode != 0
            and peak_memory_bytes is not None
            and peak_memory_bytes >= self.memory_limit_bytes
        )

    def _drain_memory_limit_messages(self) -> bool:
        exceeded = False
        for _ in range(MAX_COMPLETION_MESSAGES):
            if self._closed:
                break
            message = wintypes.DWORD()
            completion_key = ctypes.c_size_t()
            overlapped = ctypes.c_void_p()
            ok = self._kernel32.GetQueuedCompletionStatus(
                self._completion_port,
                ctypes.byref(message),
                ctypes.byref(completion_key),
                ctypes.byref(overlapped),
                0,
            )
            if not ok:
                error = ctypes.get_last_error()
                if error == WAIT_TIMEOUT:
                    break
                raise _last_error("GetQueuedCompletionStatus")
            if message.value in {
                JOB_OBJECT_MSG_PROCESS_MEMORY_LIMIT,
                JOB_OBJECT_MSG_JOB_MEMORY_LIMIT,
            }:
                exceeded = True
        else:
            raise WindowsJobError("Windows Job Object completion queue did not quiesce")
        return exceeded

    def close(self) -> None:
        """Close both handles; kill-on-close prevents surviving descendants."""
        if self._closed:
            return
        self._closed = True
        completion_port = getattr(self, "_completion_port", None)
        job = getattr(self, "_job", None)
        if completion_port:
            self._kernel32.CloseHandle(completion_port)
            self._completion_port = None
        if job:
            self._kernel32.CloseHandle(job)
            self._job = None

    def __enter__(self) -> WindowsJob:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def create_windows_job(memory_limit_bytes: int | None) -> WindowsJob | None:
    """Create the mandatory Windows boundary, or no-op on POSIX platforms."""
    if os.name != "nt":
        return None
    return WindowsJob(memory_limit_bytes)


__all__ = ["WindowsJob", "WindowsJobError", "create_windows_job"]
