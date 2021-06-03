# -*- coding: utf-8 -*-

# Copyright (c) IBM Corporation 2020
# Apache License, Version 2.0 (see https://opensource.org/licenses/Apache-2.0)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import tempfile

from ansible_collections.ibm.ibm_zos_core.plugins.module_utils import (
    data_set,
)

from ansible_collections.ibm.ibm_zos_core.plugins.module_utils.import_handler import (
    MissingZOAUImport,
)

try:
    from zoautil_py import Datasets
except Exception:
    Datasets = MissingZOAUImport()


INITIAL_PRM_MEMBER = """/* Initial file to look like BPXPRM */
/* some settings at the top */
something = something else
anotherthing = something I forgot

/* This mount shouldn't change */
MOUNT FILESYSTEM('IMSTESTU.ZZZ.KID.GA.ZFS')
      MOUNTPOINT('/python3')
      TYPE('zFS')
      MODE(RDWR)
      SETUID
      WAIT
      SECURITY
      AUTOMOVE
"""

# SHELL_EXECUTABLE = "/usr/lpp/rsusr/ported/bin/bash"
SHELL_EXECUTABLE = "/bin/sh"


def get_sysname(hosts):
    results = hosts.all.shell(
        cmd="sysvar SYSNAME",
        executable=SHELL_EXECUTABLE,
        stdin="",
    )
    response = ""
    for result in results:
        if len(result) > 2:
            response = result
            break
    return response


def populate_tmpfile():
    tmp_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
    tmp_file_filename = tmp_file.name
    # tmp_file.close()
    # with open(tmp_file_filename, "w") as fh:
    tmp_file.write(INITIAL_PRM_MEMBER)
    return tmp_file_filename


def create_sourcefile(hosts):
    starter = get_sysname(hosts).split(".")[0].upper()
    if len(starter) < 2:
        starter = "IMSTESTU"
    thisfile = starter + ".TST.MNT.ZFS"
    print(
        "csf: starter={0} thisfile={1} is type {2}".format(
            starter, thisfile, str(type(thisfile))
        )
    )
    # fs_du = data_set.DataSetUtils(thisfile)
    # fs_exists = fs_du.exists()
    # if fs_exists is False:
    hosts.all.shell(
        cmd="zfsadm define -aggregate "
        + thisfile
        + " -volumes IMSCN1 -cylinders 800 1",
        executable=SHELL_EXECUTABLE,
        stdin="",
    )
    hosts.all.shell(
        cmd="zfsadm format -aggregate " + thisfile,
        executable=SHELL_EXECUTABLE,
        stdin="",
    )
    return thisfile


def test_basic_mount(ansible_zos_module):
    hosts = ansible_zos_module
    srcfn = create_sourcefile(hosts)
    try:
        mount_result = hosts.all.zos_mount(
            src=srcfn, path="/pythonx", fs_type="ZFS", state="mounted"
        )
        for result in mount_result.values():
            assert result.get("rc") == 0
            assert result.get("stdout") != ""
            assert result.get("changed") is True
    finally:
        hosts.all.zos_mount(
            src=srcfn,
            path="/pythonx",
            fs_type="ZFS",
            state="absent",
        )
        hosts.all.file(path="/pythonx/", state="absent")


def test_double_mount(ansible_zos_module):
    hosts = ansible_zos_module
    srcfn = create_sourcefile(hosts)
    try:
        hosts.all.zos_mount(src=srcfn, path="/pythonx", fs_type="ZFS", state="mounted")
        # The duplication here is intentional... want to make sure it is seen
        mount_result = hosts.all.zos_mount(
            src=srcfn, path="/pythonx", fs_type="ZFS", state="mounted"
        )
        for result in mount_result.values():
            assert result.get("rc") == 0
            assert "already mounted" in result.get("comment")
            assert result.get("stdout") != ""
            assert result.get("changed") is False
    finally:
        hosts.all.zos_mount(
            src=srcfn,
            path="/pythonx",
            fs_type="ZFS",
            state="absent",
        )
        hosts.all.file(path="/pythonx/", state="absent")


def test_basic_mount_with_bpx_nocomment_nobackup(ansible_zos_module):
    hosts = ansible_zos_module
    srcfn = create_sourcefile(hosts)

    tmp_file_filename = "/tmp/testfile.txt"
    with open(tmp_file_filename, 'w') as infile:
        infile.write(INITIAL_PRM_MEMBER)

    hosts.all.copy(
        src=tmp_file_filename,
        dest=tmp_file_filename,
    )

    dest = "USER.TEST.BPX.PDS"
    dest_path = "USER.TEST.BPX.PDS(AUTO1)"
    src_file = tmp_file_filename

    hosts.all.zos_data_set(
        name=dest,
        type="pdse",
        space_primary=5,
        space_type="M",
        record_format="fba",
        record_length=80,
    )
    print("\nbnn-Copying {0} to {1}\n".format(src_file, dest_path))
    hosts.all.shell(
        cmd="cp " + tmp_file_filename + " \"//'" + dest_path + "'\"",
        executable=SHELL_EXECUTABLE,
        stdin="",
    )
    try:
        mount_result = hosts.all.zos_mount(
            src=srcfn,
            path="/pythonx",
            fs_type="ZFS",
            state="mounted",
            persistent=dict(data_set_name=dest_path),
        )

        for result in mount_result.values():
            assert result.get("rc") == 0
            assert result.get("stdout") != ""
            assert result.get("changed") is True

    finally:
        hosts.all.zos_mount(
            src=srcfn,
            path="/pythonx",
            fs_type="ZFS",
            state="absent",
        )
        hosts.all.file(path=tmp_file_filename, state="absent")
        hosts.all.file(path="/pythonx/", state="absent")


def test_basic_mount_with_bpx_comment_backup(ansible_zos_module):
    hosts = ansible_zos_module
    srcfn = create_sourcefile(hosts)

    tmp_file_filename = "/tmp/testfile.txt"
    # change to write to localhost
    with open(tmp_file_filename, 'w') as infile:
        infile.write(INITIAL_PRM_MEMBER)

    # because this is with/open, it is showing the content on the ansible server
    with open(tmp_file_filename, 'r') as infile:
        data = infile.read()

    print("\nbcb-pre-copy-original  result:\n{0}\n".format(data))
    print("\n====================================================\n")

    # put the pre-copy onto targets...trying content to get around translation
    hosts.all.copy(
        # src=tmp_file_filename,
        content=INITIAL_PRM_MEMBER,
        dest=tmp_file_filename,
    )
    # discovery: chtag -t -c ISO8859-1 bad2.flag.txt makes it readable at console
    # Pull the values of the file once copied to the target
    hosts.all.shell(
        cmd="chtag -t -c ISO8859-1 " + tmp_file_filename,
        executable=SHELL_EXECUTABLE,
        stdin="",
    )
    results = hosts.all.shell(
        cmd="cat " + tmp_file_filename,
        executable=SHELL_EXECUTABLE,
        stdin="",
    )
    for result in results.values():
        print("\nbcb-destination result: {0}\n".format(result.get("stdout")))

    print("\n====================================================\n")

    dest = "USER.TEST.BPX.PDS"
    dest_path = "USER.TEST.BPX.PDS(AUTO2)"
    back_dest_path = "USER.TEST.BPX.PDS(AUTO2BAK)"
    src_file = tmp_file_filename

    hosts.all.zos_data_set(
        name=dest,
        type="pdse",
        space_primary=5,
        space_type="M",
        record_format="fba",
        record_length=80,
    )

    print("\nbcb-Copying {0} to {1}\n".format(src_file, dest_path))

    hosts.all.shell(
        cmd="cp " + tmp_file_filename + " \"//'" + dest_path + "'\"",
        executable=SHELL_EXECUTABLE,
        stdin="",
    )

    data = ""

    try:
        mount_result = hosts.all.zos_mount(
            src=srcfn,
            path="/pythonx",
            fs_type="ZFS",
            state="mounted",
            persistent=dict(
                data_set_name=dest_path,
                backup="Yes",
                backup_name=back_dest_path,
            ),
            tabcomment=[
                "bpxtablecomment - try this",
                "second line of comment"
            ],
        )
        # copying from dataset to make editable copy on target
        test_tmp_file_filename = tmp_file_filename + "-a"

        hosts.all.shell(
            cmd="cp \"//'" + dest_path + "'\" " + test_tmp_file_filename,
            executable=SHELL_EXECUTABLE,
            stdin="",
        )
        hosts.all.shell(
            cmd="chtag -t -c ISO8859-1 " + test_tmp_file_filename,
            executable=SHELL_EXECUTABLE,
            stdin="",
        )
        results = hosts.all.shell(
            cmd="cat " + test_tmp_file_filename,
            executable=SHELL_EXECUTABLE,
            stdin=""
        )
        data = ""
        for result in results.values():
            print("\nbcb-postmount result: {0}\n".format(result.get("stdout")))
            data += result.get("stdout")

        print("\n====================================================\n")

        for result in mount_result.values():
            assert result.get("rc") == 0
            assert result.get("stdout") != ""
            assert result.get("changed") is True

        assert srcfn in data
        assert "bpxtablecomment - try this" in data
        # fs_du = data_set.DataSetUtils(back_dest_path)
        # fs_exists = fs_du.exists()
        # assert fs_exists
    finally:
        hosts.all.zos_mount(
            src=srcfn,
            path="/pythonx",
            fs_type="ZFS",
            state="absent",
        )
        hosts.all.file(path=tmp_file_filename, state="absent")
        hosts.all.file(path=test_tmp_file_filename, state="absent")
        hosts.all.file(path="/pythonx/", state="absent")
