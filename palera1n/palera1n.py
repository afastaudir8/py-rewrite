# imports
from argparse import Namespace
from deps import iBootPatcher, Gaster, irecovery
from img4 import IMG4
from logger import colors
from pathlib import Path
from ramdisk import Ramdisk
import logger
import os
import plistlib
import requests
import remotezip
import subprocess as sp
import sys
import tempfile
import time
import utils


class palera1n:
    def __init__(self, in_package: bool, args: Namespace) -> None:
        self.in_package = in_package
        self.args = args
        
        # Binaries
        self.ibootpatcher = None
        self.irecovery = None
        self.kernelpatcher = None
        self.gaster = None
        
        # Directories
        self.data_dir = None
        self.tmp = None
        
        # Device info
        self.cpid = None
        self.model = None
        self.deviceid = None
        self.version = None
        
        # Other variables
        self.ipsw = None
        self.os = sp.getoutput("uname")

    def main(self) -> None:
        print(colors["bold"] + f"palera1n | version {utils.get_version()}" + colors["reset"])
        print("Written by Nebula and Mineek | 'ramdisk' by Nathan | Loader app by Amy")
        
        if self.in_package:
            logger.debug(f"Running from package, not cloned repo.", self.args.debug)
        
        logger.debug(f"Running on {self.os}", self.args.debug)
        
        # Create data directory
        self.data_dir = utils.get_storage_dir()
        logger.debug(f"Data directory is '{self.data_dir}'", self.args.debug)
        Path(self.data_dir).mkdir(exist_ok=True, parents=True)
        
        # Dependency check
        logger.log("Checking for dependencies...")
        logger.debug("Checking for iBoot64Patcher...", self.args.debug)
        self.ibootpatcher = self.data_dir / "iBoot64Patcher"
        if iBootPatcher(self.data_dir, self.args).exists_in_data_dir():
            logger.debug("iBoot64Patcher found!", self.args.debug)
        else:
            logger.debug("iBoot64Patcher not found in path", self.args.debug)
            iBootPatcher(self.data_dir, self.args).download()
        
        logger.debug("Checking for gaster...", self.args.debug)
        self.gaster = self.data_dir / "gaster"
        if Gaster(self.data_dir, self.args).exists_in_data_dir():
            logger.debug("gaster found!", self.args.debug)
        else:
            logger.debug("gaster not found in path", self.args.debug)
            Gaster(self.data_dir, self.args).download()
        
        logger.debug("Checking for irecovery...", self.args.debug)
        self.irecovery = self.data_dir / "irecovery"
        if irecovery(self.data_dir, self.args).exists_in_data_dir():
            logger.debug("irecovery found!", self.args.debug)
        else:
            logger.debug("irecovery not found in path", self.args.debug)
            irecovery(self.data_dir, self.args).download()
        
        if (utils.check_is_connected() is not True):
            logger.log("Waiting for devices...")
        while (utils.check_is_connected() is not True):
            time.sleep(1)
        
        # Get device info, then debug log them
        if self.args.dfu:
            self.version = self.args.dfu
        else:
            self.version = utils.device_info("normal", "ProductVersion", self.data_dir, self.args)

        if (self.version.startswith("15") is not True):
            logger.error("Your device is not supported. (iOS 15.x required, currently running iOS {})".format(self.version))
            sys.exit(1)
        
        if (utils.device_info("normal", "CPUArchitecture", self.data_dir, self.args) == "arm64e"):
            logger.error("Your device is not supported. (arm64e architecture detected)")
            sys.exit(1)
        
        logger.log("Hello, {} on {}!".format(utils.device_info("normal", "ProductType", self.data_dir, self.args), self.version))
        
        if (utils.check_state('dfu') is not True):
            logger.debug("NOT IN DFU", self.args.debug)
            if (utils.check_state('recovery') is not True):
                logger.log("Entering recovery mode...")
                utils.enter_recovery(utils.device_info("normal", "UniqueDeviceID", self.data_dir, self.args))
                utils.wait("recovery")
                logger.log("Entered recovery mode.")
            utils.guide_to_dfu(utils.device_info("recovery", "CPID", self.data_dir, self.args), utils.device_info("recovery", "PRODUCT", self.data_dir, self.args), self.data_dir, self.args)

        utils.wait("dfu")
        
        logger.log("Getting device info")
        self.cpid = utils.device_info("recovery", "CPID", self.data_dir, self.args)
        self.model = utils.device_info("recovery", "MODEL", self.data_dir, self.args)
        self.deviceid = utils.device_info("recovery", "PRODUCT", self.data_dir, self.args)
        logger.debug(f"CPID: {self.cpid}, MODEL: {self.model}, ID: {self.deviceid}", self.args.debug)

        exit(0)
        
        # Check if the device is pwned already, if not, then use gaster
        if utils.check_pwned(self.data_dir, self.args) is False:
            logger.log("Pwning device")
            Gaster(self.data_dir, self.args).run("pwn")
            Gaster(self.data_dir, self.args).run("reset")
        
        # Get IPSW
        if self.args.ipsw:
            self.ipsw = self.args.ipsw
        else:
            res = requests.get(f"https://api.ipsw.me/v4/device/{self.deviceid}?type=ipsw")
            firmwares = res.json()["firmwares"]
            for firmware in firmwares:
                if firmware["version"] == self.version:
                    self.ipsw = firmware["url"]
                
            if self.ipsw is None or self.ipsw == "":
                logger.error("IPSW could not be fetched! Please supply one with --ipsw")
                sys.exit(1)
        
        # Create tmp folder for ramdisk
        if self.args.restore_rootfs or not Path(self.data_dir / f"blobs/{self.deviceid}_{self.version}.shsh2").exists():
            with tempfile.TemporaryDirectory() as rd_tmp:
                rd = Ramdisk(self.args, self.in_package, self.data_dir, rd_tmp, self.cpid, self.model, self.deviceid)
                
                rd.create("15.6.1" if ("15.7", "15.7.1") in self.version else self.version, rootless=True if self.args.rootless else False)
                rd.boot()
                
                if self.args.restore_rootfs:
                    rd.restore_rootfs()
                else:
                    rd.install(self.ipsw)
        
        # tmp folder for everything else
        with tempfile.TemporaryDirectory() as tmp:
            self.tmp = Path(tmp)
            
            if self.args.semi_tethered or self.args.rootless:
                utils.wait("normal")
            else:
                utils.wait("recovery")
            time.sleep(3)
            utils.wait("dfu")
            
            # Now we check if boot files exist
            if not Path(self.data_dir / f"boot/{self.deviceid}_{self.version}/ibot.img4").exists():
                logger.log(f"Creating boot files for {self.version}")
                    
                with remotezip.RemoteZip(self.ipsw) as ipsw:
                    ipsw.extract("BuildManifest.plist", path=self.tmp)
                    with open(self.tmp / "BuildManifest.plist", "rb") as f:
                        plist = plistlib.load(f)
                    
                    for the_dict in plist["BuildIdentities"]:
                        if the_dict["ApChipID"] == self.cpid:
                            identity = the_dict
                            break
                    
                    print("Downloading files")
                    ipsw.extract(utils.get_path(identity, "iBSS"), path=self.tmp)
                    ipsw.extract(utils.get_path(identity, "iBoot"), path=self.tmp)
                
                img4 = IMG4(self.args, self.in_package, self.data_dir / f"blobs/{self.deviceid}_{self.version}.shsh2", self.data_dir, self.tmp)
                
                print("Patching iBSS")
                Gaster(self.data_dir, self.args).run("decrypt", decrypt_input=(self.tmp / utils.get_path(identity, "iBSS").replace("Firmware/dfu/", "")), decrypt_output=(self.tmp / "iBSS.dec"))
                iBootPatcher(self.data_dir, self.args).run((self.tmp / "iBSS.dec"), (self.tmp / "iBSS.patched"))
                img4.im4p_to_img4((self.tmp / "iBSS.patched"), (self.data_dir / f"boot/{self.deviceid}_{self.version}/iBSS.img4"), "ibss")
                
                print("Patching iBoot")
                Gaster(self.data_dir, self.args).run("decrypt", decrypt_input=(self.tmp / utils.get_path(identity, "iBoot").replace("Firmware/dfu/", "")), decrypt_output=(self.tmp / "ibot.dec"))
                iBootPatcher(self.data_dir, self.args).run((self.tmp / "ibot.dec"), (self.tmp / "ibot.patched"), nvram_unlock=True, fsboot=True, boot_args=f"{'serial=3' if self.args.serial else '-v'} keepsyms=1 debug=0x2014e{'rd=disk0s1s8' if self.args.semi_tethered else ''}")
                with open((self.tmp / "ibot.patched"), "wb") as f:
                    content = f.read()
                    new = content.replace(b"/kernelcache", b"/kernelcachd")
                    f.truncate(0)
                    f.write(new)
                img4.im4p_to_img4((self.tmp / "ibot.patched"), (self.data_dir / f"boot/{self.deviceid}_{self.version}/ibot.img4"), "ibec" if ("iPhone8", "iPad5", "iPad6") in self.deviceid else "ibss")
                
            # Lets actually boot the device
            if utils.check_pwned() is False:
                print("Pwning device")
                Gaster(self.data_dir, self.args).run("pwn")
                Gaster(self.data_dir, self.args).run("reset")
            
            irec = irecovery(self.data_dir, self.args)
            
            irec.run("file", file=(self.data_dir / f"boot/{self.deviceid}_{self.version}/iBSS.img4"))
            irec.run("file", file=(self.data_dir / f"boot/{self.deviceid}_{self.version}/ibot.img4"))
            irec.run("cmd", command="fsboot")
        
        logger.info("Done!")
        logger.info("The device should now boot to jailbroken iOS")
        logger.info("If you have any issues or questions, please ask in our Discord server: https://dsc.gg/palera1n")
        logger.info("Also, this is free and open source software! Feel free to donate to my Patreon if you enjoy :)")
        print(f"    {colors['green']}https://patreon.com/nebulalol")
