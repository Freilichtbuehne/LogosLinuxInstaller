import datetime
import glob
import logging
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import config
from msg import cli_msg
from msg import logos_acknowledge_question
from msg import logos_error
from msg import logos_info
from msg import logos_warn
from utils import check_libs
from utils import checkDependencies
from utils import checkDependenciesLogos9
from utils import checkDependenciesLogos10
from utils import clean_all
from utils import cli_download
from utils import curses_menu
from utils import get_runmode
from utils import getLogosReleases
from utils import getWineBinOptions
from utils import make_skel
from utils import write_config
from wine import createWineBinaryList
from wine import get_wine_env
from wine import heavy_wineserver_wait
from wine import initializeWineBottle
from wine import install_msi
from wine import installFonts
from wine import installD3DCompiler
from wine import run_logos
from wine import wine_reg_install
from wine import winetricks_install


def logos_download(uri, destination):
    if config.DIALOG in ['curses', 'tk']:
        cli_download(uri, destination)

def logos_reuse_download(SOURCEURL, FILE, TARGETDIR):
    DIRS = [
        config.INSTALLDIR,
        os.getcwd(),
        config.MYDOWNLOADS,
    ]
    FOUND = 1
    for i in DIRS:
        if os.path.isfile(os.path.join(i, FILE)):
            logos_info(f"{FILE} exists in {i}. Using it…")
            shutil.copy(os.path.join(i, FILE), TARGETDIR)
            logos_progress("Copying…", f"Copying {FILE}\ninto {TARGETDIR}")
            FOUND = 0
            break
    if FOUND == 1:
        logos_info(f"{FILE} does not exist. Downloading…")
        logos_download(SOURCEURL, os.path.join(config.MYDOWNLOADS, FILE))
        shutil.copy(os.path.join(config.MYDOWNLOADS, FILE), TARGETDIR)
        logos_progress("Copying…", f"Copying: {FILE}\ninto: {TARGETDIR}")

def getAppImage():
    wine64_appimage_full_filename = Path(config.WINE64_APPIMAGE_FULL_FILENAME)
    appdir_bindir = Path(config.APPDIR_BINDIR)
    dest_path = appdir_bindir / wine64_appimage_full_filename
    if dest_path.is_file():
        return
    else:
        logos_reuse_download(config.WINE64_APPIMAGE_FULL_URL, config.WINE64_APPIMAGE_FULL_FILENAME, config.APPDIR_BINDIR)

def chooseProduct():
    BACKTITLE = "Choose Product Menu"
    TITLE = "Choose Product"
    QUESTION_TEXT = "Choose which FaithLife product the script should install:"
    if config.FLPRODUCT is None:
        options = ["Logos", "Verbum", "Exit"]
        productChoice = curses_menu(options, TITLE, QUESTION_TEXT)
    else:
        productChoice = config.FLPRODUCT

    print("productChoice:" + str(productChoice))
    if str(productChoice).startswith("Logos"):
        if config.VERBOSE:
            print("Installing Logos Bible Software")
        config.FLPRODUCT = "Logos"
        config.FLPRODUCTi = "logos4" #This is the variable referencing the icon path name in the repo.
        config.VERBUM_PATH = "/"
    elif str(productChoice).startswith("Verbum"):
        if config.VERBOSE:
            print("Installing Verbum Bible Software")
        config.FLPRODUCT = "Verbum"
        config.FLPRODUCTi = "verbum" #This is the variable referencing the icon path name in the repo.
        config.VERBUM_PATH = "/Verbum/"
    elif str(productChoice).startswith("Exit"):
        logos_error("Exiting installation.", "")
    else:
        logos_error("Unknown product. Installation canceled!", "")

    # Set icon variables.
    if config.LOGOS_ICON_URL is None:
        config.LOGOS_ICON_URL = "https://raw.githubusercontent.com/ferion11/LogosLinuxInstaller/master/img/" + config.FLPRODUCTi + "-128-icon.png"
    if config.LOGOS_ICON_FILENAME is None:
        config.LOGOS_ICON_FILENAME = os.path.basename(config.LOGOS_ICON_URL)

def getLogosReleaseVersion(releases):
    TITLE=f"Choose {config.FLPRODUCT} {config.TARGETVERSION} Release"
    QUESTION_TEXT=f"Which version of {config.FLPRODUCT} {config.TARGETVERSION} do you want to install?"
    logos_release_version = curses_menu(releases, TITLE, QUESTION_TEXT)

    if logos_release_version is not None:
        config.LOGOS_RELEASE_VERSION = logos_release_version
    else:
        print("Failed to fetch LOGOS_RELEASE_VERSION.")

def chooseVersion():
    BACKTITLE = "Choose Version Menu"
    TITLE = "Choose Product Version"
    QUESTION_TEXT = f"Which version of {config.FLPRODUCT} should the script install?"
    if config.TARGETVERSION is None or config.TARGETVERSION == "":
        options = ["10", "9", "Exit"]
        versionChoice = curses_menu(options, TITLE, QUESTION_TEXT)
    else:
        versionChoice = config.TARGETVERSION
   
    checkDependencies()
    if "10" in versionChoice:
        checkDependenciesLogos10()
        config.TARGETVERSION = "10"
    elif "9" in versionChoice:
        checkDependenciesLogos9()
        config.TARGETVERSION = "9"
    elif versionChoice == "Exit.":
        exit()
    else:
        logos_error("Unknown version. Installation canceled!", "")

def logos_setup():
    if config.LOGOS64_URL is None or config.LOGOS64_URL == "":
        print(config.TARGETVERSION, config.VERBUM_PATH, config.LOGOS_RELEASE_VERSION, config.FLPRODUCT)
        config.LOGOS64_URL = f"https://downloads.logoscdn.com/LBS{config.TARGETVERSION}{config.VERBUM_PATH}Installer/{config.LOGOS_RELEASE_VERSION}/{config.FLPRODUCT}-x64.msi"

    if config.FLPRODUCT == "Logos":
        config.LOGOS_VERSION = config.LOGOS64_URL.split('/')[5]
    elif config.FLPRODUCT == "Verbum":
        config.LOGOS_VERSION = config.LOGOS64_URL.split('/')[6]
    # else:
    #     logos_error("FLPRODUCT not set in config. Please update your config to specify either 'Logos' or 'Verbum'.", "")

    config.LOGOS64_MSI = os.path.basename(config.LOGOS64_URL)
    
    if config.INSTALLDIR is None:
        config.INSTALLDIR = f"{os.getenv('HOME')}/{config.FLPRODUCT}Bible{config.TARGETVERSION}"
    if config.APPDIR is None or config.APPDIR == "":
        config.APPDIR = f"{config.INSTALLDIR}/data"
    if config.APPDIR_BINDIR is None or config.APPDIR_BINDIR == "":
        config.APPDIR_BINDIR = f"{config.APPDIR}/bin"

def chooseInstallMethod():
    if config.WINEPREFIX is None:
        config.WINEPREFIX = os.path.join(config.APPDIR, "wine64_bottle")

    if config.WINE_EXE is None:
        logos_info("Creating binary list.")
        binaries = createWineBinaryList()
        WINEBIN_OPTIONS = getWineBinOptions(binaries)

        BACKTITLE="Choose Wine Binary Menu"
        TITLE="Choose Wine Binary"
        QUESTION_TEXT=f"Which Wine binary and install method should the script use to install {config.FLPRODUCT} v{config.LOGOS_VERSION} in {config.INSTALLDIR}?"

        installationChoice = curses_menu(WINEBIN_OPTIONS, TITLE, QUESTION_TEXT)
        WINECHOICE_CODE = installationChoice[0]
        config.WINE_EXE = installationChoice[1]

        config.WINEBIN_CODE = WINECHOICE_CODE
        if config.VERBOSE:
            print(f"chooseInstallMethod(): WINEBIN_CODE: {WINECHOICE_CODE}; WINE_EXE: {config.WINE_EXE}")

def checkExistingInstall(app=None):
    # Now that we know what the user wants to install and where, determine whether an install exists and whether to continue.
    if app is not None:
        app.install_q.put("Checking for existing installation...")
        app.root.event_generate("<<UpdateInstallText>>")

    if os.path.isdir(config.INSTALLDIR):
        if config.VERBOSE:
            print(f"INSTALLDIR: {config.INSTALLDIR}")
        drive_c = f"{config.WINEPREFIX}/drive_c"
        names = ['Logos.exe', 'Verbum.exe']
        if os.path.isdir(drive_c) and any(glob.glob(f"{drive_c}/**/{n}", recursive=True) for n in names):
            global EXISTING_LOGOS_INSTALL
            EXISTING_LOGOS_INSTALL = 1
            print(f"An install was found at {config.INSTALLDIR}. Please remove/rename it or use another location by setting the INSTALLDIR variable.")
            return True
        else:
            global EXISTING_LOGOS_DIRECTORY
            EXISTING_LOGOS_DIRECTORY = 1
            print(f"A directory exists at {config.INSTALLDIR}. Please remove/rename it or use another location by setting the INSTALLDIR variable.")
            return True
    else:
        if config.VERBOSE:
            print(f"Installing to an empty directory at {config.INSTALLDIR}.")

    if app is not None:
        app.root.event_generate("<<CheckExistingInstallDone>>")

def beginInstall(app):
    if app is not None:
        app.install_q.put("Preparing installation folder...")
        app.root.event_generate("<<UpdateInstallText>>")

    if config.SKEL == True:
        if config.VERBOSE:
            print("Making a skeleton install of the project only. Exiting after completion.")
        make_skel("none.AppImage")
        exit(0)

    if config.WINEBIN_CODE:
        if config.WINEBIN_CODE.startswith("AppImage"):
            check_libs(["libfuse"])
            if config.VERBOSE:
                print(f"Installing {config.FLPRODUCT} Bible {config.TARGETVERSION} using {config.WINE64_APPIMAGE_FULL_VERSION} AppImage…")
            make_skel(config.WINE64_APPIMAGE_FULL_FILENAME)
            # exporting PATH to internal use if using AppImage, doing backup too:
            os.environ["OLD_PATH"] = os.environ["PATH"]
            os.environ["PATH"] = f"{config.APPDIR_BINDIR}:{os.environ['PATH']}"
            # Geting the AppImage:
            getAppImage()
            os.chmod(f"{config.APPDIR_BINDIR}/{config.WINE64_APPIMAGE_FULL_FILENAME}", 0o755)
            config.WINE_EXE = f"{config.APPDIR_BINDIR}/wine64"
        elif config.WINEBIN_CODE in ["System", "Proton", "PlayOnLinux", "Custom"]:
            if config.VERBOSE:
                print(f"Installing {config.FLPRODUCT} Bible {config.TARGETVERSION} using a {config.WINEBIN_CODE} WINE64 binary…")
            make_skel("none.AppImage")
        else:
            print("WINEBIN_CODE error. Installation canceled!")
            sys.exit(1)
    else:
        if config.VERBOSE:
            print("WINEBIN_CODE is not set in your config file.")

    if config.VERBOSE:
        wine_version = subprocess.check_output([config.WINE_EXE, "--version"]).decode().strip()
        print(f"Using: {wine_version}")

    # Set WINESERVER_EXE based on WINE_EXE.
    if config.WINESERVER_EXE is None:
        wineserver_path = os.path.join(os.path.dirname(config.WINE_EXE), "wineserver")
        if os.path.exists(wineserver_path):
            config.WINESERVER_EXE = wineserver_path

        else:
            print(f"{wineserver_path} not found. Please either add it or create a symlink to it, and rerun.")

def downloadWinetricks():
    logos_reuse_download(config.WINETRICKS_URL, "winetricks", config.APPDIR_BINDIR)
    os.chmod(f"{config.APPDIR_BINDIR}/winetricks", 0o755)

def setWinetricks():
    # Check if local winetricks version available; else, download it
    if config.WINETRICKSBIN is None:
        local_winetricks_path = shutil.which('winetricks')
        if local_winetricks_path is not None:
            # Check if local winetricks version is up-to-date; if so, offer to use it or to download; else, download it
            local_winetricks_version = subprocess.check_output(["winetricks", "--version"]).split()[0]
            if str(local_winetricks_version) >= "20220411":
                backtitle = "Choose Winetricks Menu"
                title = "Choose Winetricks"
                question_text = "Should the script use the system's local winetricks or download the latest winetricks from the Internet? The script needs to set some Wine options that FLPRODUCT requires on Linux."

                options = ["1: Use local winetricks.", "2: Download winetricks from the Internet"]
                winetricks_choice = curses_menu(options, title, question_text)

                print(f"winetricks_choice: {winetricks_choice}")
                if winetricks_choice.startswith("1"):
                    print("Setting winetricks to the local binary…")
                    config.WINETRICKSBIN = local_winetricks_path
                elif winetricks_choice.startswith("2"):
                    downloadWinetricks()
                    config.WINETRICKSBIN = os.path.join(config.APPDIR_BINDIR, "winetricks")
                else:
                    sys.exit("Installation canceled!")
            else:
                print("The system's winetricks is too old. Downloading an up-to-date winetricks from the Internet...")
                downloadWinetricks()
                config.WINETRICKSBIN = os.path.join(config.APPDIR_BINDIR, "winetricks")
        else:
            print("Local winetricks not found. Downloading winetricks from the Internet…")
            downloadWinetricks()
            config.WINETRICKSBIN = os.path.join(config.APPDIR_BINDIR, "winetricks")

    print("Winetricks is ready to be used.")

def getPremadeWineBottle():
    if config.VERBOSE:
        print("Installing pre-made wineBottle 64bits…")
    logos_reuse_download(config.WINE64_BOTTLE_TARGZ_URL, config.WINE64_BOTTLE_TARGZ_NAME, config.WORKDIR)
    shutil.unpack_archive(os.path.join(config.WORKDIR, config.WINE64_BOTTLE_TARGZ_NAME), config.APPDIR)
    logos_progress("Extracting…", "Extracting: " + config.WINE64_BOTTLE_TARGZ_NAME + "\ninto: " + config.APPDIR)

## END WINE BOTTLE AND WINETRICKS FUNCTIONS
## BEGIN LOGOS INSTALL FUNCTIONS 
def get_logos_executable():
    PRESENT_WORKING_DIRECTORY = config.PRESENT_WORKING_DIRECTORY
    HOME = os.environ.get('HOME')
    # This VAR is used to verify the downloaded MSI is latest
    if config.LOGOS_EXECUTABLE is None:
        config.LOGOS_EXECUTABLE = f"{config.FLPRODUCT}_v{config.LOGOS_VERSION}-x64.msi"
    
    #cli_continue_question(f"Now the script will check for the MSI installer. Then it will download and install {FLPRODUCT} Bible at {WINEPREFIX}. You will need to interact with the installer. Do you wish to continue?", "The installation was cancelled!", "")
    
    # Getting and installing {FLPRODUCT} Bible
    # First check current directory to see if the .MSI is present; if not, check user's Downloads/; if not, download it new. Once found, copy it to WORKDIR for future use.
    if config.VERBOSE:
        print(f"Installing {config.FLPRODUCT}Bible 64bits…")
    if os.path.isfile(f"{PRESENT_WORKING_DIRECTORY}/{config.LOGOS_EXECUTABLE}"):
        if config.VERBOSE:
            print(f"{config.LOGOS_EXECUTABLE} exists. Using it…")
        shutil.copy(f"{PRESENT_WORKING_DIRECTORY}/{config.LOGOS_EXECUTABLE}", f"{config.APPDIR}/")
    elif os.path.isfile(f"{config.MYDOWNLOADS}/{config.LOGOS_EXECUTABLE}"):
        if config.VERBOSE:
            print(f"{config.LOGOS_EXECUTABLE} exists. Using it…")
        shutil.copy(f"{config.MYDOWNLOADS}/{config.LOGOS_EXECUTABLE}", f"{config.APPDIR}/")
    else:
        if config.VERBOSE:
            print(f"{config.LOGOS_EXECUTABLE} does not exist. Downloading…")
        logos_download(config.LOGOS64_URL, f"{config.MYDOWNLOADS}/")
        shutil.move(f"{config.MYDOWNLOADS}/{config.LOGOS64_MSI}", f"{config.MYDOWNLOADS}/{config.LOGOS_EXECUTABLE}")
        shutil.copy(f"{config.MYDOWNLOADS}/{config.LOGOS_EXECUTABLE}", f"{config.APPDIR}/")

def installLogos9(app):
    if app is not None:
        app.install_q.put("Configuring wine bottle and installing app...")
        app.root.event_generate("<<UpdateInstallText>>")

    getPremadeWineBottle()
    setWinetricks()
    installFonts()
    installD3DCompiler()
    get_logos_executable()
    install_msi()
    env = get_wine_env()

    if config.VERBOSE:
        print(f"======= Set {config.FLPRODUCT}Bible Indexing to Vista Mode: =======")
    subprocess.run(f'{config.WINE_EXE} reg add "HKCU\\Software\\Wine\\AppDefaults\\{config.FLPRODUCT}Indexer.exe" /v Version /t REG_SZ /d vista /f', shell=True, env=env)
    if config.VERBOSE:
        print(f"======= {config.FLPRODUCT}Bible logging set to Vista mode! =======")

def installLogos10(app=None):
    if app is not None:
        app.install_q.put("Configuring wine bottle and installing app...")
        app.root.event_generate("<<UpdateInstallText>>")

    reg_file = os.path.join(config.WORKDIR, 'disable-winemenubuilder.reg')
    gdi_file = os.path.join(config.WORKDIR, 'renderer_gdi.reg')
    with open(reg_file, 'w') as f:
        f.write('''REGEDIT4

[HKEY_CURRENT_USER\Software\Wine\DllOverrides]
"winemenubuilder.exe"=""
''')
    with open(gdi_file, 'w') as f:
        f.write('''REGEDIT4

[HKEY_CURRENT_USER\Software\Wine\Direct3D]
"DirectDrawRenderer"="gdi"
"renderer"="gdi"
''')

    wine_reg_install(reg_file)
    wine_reg_install(gdi_file)

    setWinetricks()
    installFonts()
    installD3DCompiler()

    if not config.WINETRICKS_UNATTENDED:
        winetricks_install("-q", "settings", "win10")
    else:
        winetricks_install("settings", "win10")

    get_logos_executable()
    install_msi()

def postInstall(app):
    if app is not None:
        app.install_q.put("Finishing installation...")
        app.root.event_generate("<<UpdateInstallText>>")

    if config.DEBUG:
        print("Starting postInstall")

    HOME = os.environ.get('HOME')
    config_keys = ["FLPRODUCT", "FLPRODUCTi", "TARGETVERSION", "INSTALLDIR", "APPDIR", "APPDIR_BINDIR", "WINETRICKSBIN", "WINEPREFIX", "WINEBIN_CODE", "WINE_EXE", "WINESERVER_EXE", "WINE64_APPIMAGE_FULL_URL", "WINE64_APPIMAGE_FULL_FILENAME", "APPIMAGE_LINK_SELECTION_NAME", "LOGOS_EXECUTABLE", "LOGOS_EXE", "LOGOS_DIR", "LOGS", "BACKUPDIR"]

    if config.VERBOSE:
        print("postInstall config:")
        for k in config_keys:
            print(f"{k}: {config.__dict__.get(k)}")

    if os.path.isfile(config.LOGOS_EXE):
        logos_info(f"{config.FLPRODUCT} Bible {config.TARGETVERSION} installed!")

        if not os.path.isfile(config.CONFIG_FILE): # config.CONFIG_FILE is set in main() function
            os.makedirs(os.path.join(HOME, ".config", "Logos_on_Linux"), exist_ok=True)
            if os.path.isdir(os.path.join(HOME, ".config", "Logos_on_Linux")):
                write_config(config.CONFIG_FILE, config_keys)
                logos_info(f"A config file was created at {config.CONFIG_FILE}.")
            else:
                logos_warn(f"{HOME}/.config/Logos_on_Linux does not exist. Failed to create config file.")
        elif os.path.isfile(config.CONFIG_FILE):
            # Compare existing config file contents with installer config.
            current_config_file_dict = config.get_config_file_dict(config.CONFIG_FILE)
            different = False
            for key in config_keys:
                if current_config_file_dict.get(key) != config.__dict__.get(key):
                    different = True
                    break
            if different is True and logos_acknowledge_question(f"Update config file at {config.CONFIG_FILE}?", "The existing config file was not overwritten."):
                write_config(config.CONFIG_FILE, config_keys)
        else:
            # Script was run with a config file. Skip modifying the config.
            pass

        # Copy executable to config.APPDIR.
        runmode = get_runmode()
        if runmode == 'binary':
            launcher_exe = Path(f"{config.INSTALLDIR}/LogosLinuxLauncher")
            # FIXME: Confirm file copy and test desktop launcher.
            if launcher_exe.is_file():
                launcher_exe.unlink()
            shutil.copy(sys.executable, launcher_exe)
            create_shortcut()

            if config.DIALOG == 'tk':
                subprocess.Popen(str(launcher_exe))
            elif logos_acknowledge_question(f"An executable has been placed at {launcher_exe}.\nDo you want to run it now?\nNOTE: There may be an error on first execution. You can close the error dialog.", "The Script has finished. Exiting…"):
                subprocess.Popen([str(launcher_exe)])
        elif runmode == 'script':
            if config.DIALOG == 'tk':
                subprocess.Popen(sys.argv)
            elif logos_acknowledge_question(f"Run {config.FLPRODUCT} now?", "The Script has finished. Exiting…"):
                subprocess.Popen(sys.argv)
        if config.VERBOSE:
            print("The script has finished. Exiting…")
    else:
        logos_error(f"Installation failed. {config.LOGOS_EXE} not found. Exiting…\nThe {config.FLPRODUCT} executable was not found. This means something went wrong while installing {config.FLPRODUCT}. Please contact the Logos on Linux community for help.")

def install():
    prepare_install()
    finish_install()

def prepare_install():
    if config.VERBOSE:
        print(datetime.datetime.now())
    chooseProduct()  # We ask user for his Faithlife product's name and set variables.
    if config.VERBOSE:
        print(datetime.datetime.now())
    chooseVersion()  # We ask user for his Faithlife product's version, set variables, and create project skeleton.
    if config.VERBOSE:
        print(datetime.datetime.now())
    getLogosReleaseVersion(getLogosReleases())
    if config.VERBOSE:
        print(datetime.datetime.now())
    logos_setup() # We set some basic variables for the install, including retrieving the product's latest release.
    if config.VERBOSE:
        print(datetime.datetime.now())
    chooseInstallMethod()  # We ask user for his desired install method.

def finish_install(app=None):
    if app is not None:
        app.install_q.put("Beginning installation...")
        app.root.event_generate("<<UpdateInstallText>>")

    if config.VERBOSE:
        print(datetime.datetime.now())
    if checkExistingInstall(app):
        logos_error("Existing installation.")
    
    if config.VERBOSE:
        print(datetime.datetime.now())
    beginInstall(app)

    if config.VERBOSE:
        print(datetime.datetime.now())
    initializeWineBottle(app)  # We run wineboot.
    
    if config.TARGETVERSION == "10":
        if config.VERBOSE:
            print(datetime.datetime.now())
        installLogos10(app)  # We run the commands specific to Logos 10.
    elif config.TARGETVERSION == "9":
        if config.VERBOSE:
            print(datetime.datetime.now())
        installLogos9(app)  # We run the commands specific to Logos 9.
    else:
        logos_error(f"TARGETVERSION unrecognized: '{config.TARGETVERSION}'. Installation canceled!")
    
    if config.VERBOSE:
        print(datetime.datetime.now())
    
    heavy_wineserver_wait()
    
    clean_all()
    
    exes = [e for e in glob.glob(f"{config.WINEPREFIX}/drive_c/**/{config.FLPRODUCT}.exe", recursive=True) if 'Pending' not in e]
    if len(exes) < 1:
        logos_error("Logos was not installed.")
    config.LOGOS_EXE = exes[0]
    
    if config.VERBOSE:
        print(datetime.datetime.now())
    postInstall(app)
    
    # with open(config.LOGOS_LOG, "a") as f:
    #     f.write(output) # FIXME: What should be in "output"?
    
    if app is not None:
        app.root.event_generate("<<CheckInstallProgress>>")


def create_shortcut():
    # Set icon variables.
    if config.LOGOS_ICON_URL is None:
        config.LOGOS_ICON_URL = "https://raw.githubusercontent.com/ferion11/LogosLinuxInstaller/master/img/" + config.FLPRODUCTi + "-128-icon.png"
    if config.LOGOS_ICON_FILENAME is None:
        config.LOGOS_ICON_FILENAME = os.path.basename(config.LOGOS_ICON_URL)

    logos_icon_path = os.path.join(config.APPDIR, config.LOGOS_ICON_FILENAME)

    if not os.path.isfile(logos_icon_path):
        os.makedirs(config.APPDIR, exist_ok=True)
        raw_bytes = None
        try:
            with urllib.request.urlopen(config.LOGOS_ICON_URL) as f:
                raw_bytes = f.read()
        except urllib.error.URLError as e:
            logos_error(e)
        if raw_bytes is not None:
            with open(logos_icon_path, 'wb') as f:
                f.write(raw_bytes)

    desktop_entry_path = os.path.expanduser(f"~/.local/share/applications/{config.FLPRODUCT}Bible.desktop")
    if os.path.exists(desktop_entry_path):
        os.remove(desktop_entry_path)

    with open(desktop_entry_path, 'w') as desktop_file:
        desktop_file.write(f"""[Desktop Entry]
Name={config.FLPRODUCT}Bible
Comment=A Bible Study Library with Built-In Tools
Exec={config.INSTALLDIR}/LogosLinuxLauncher
Icon={logos_icon_path}
Terminal=false
Type=Application
Categories=Education;
""")

    os.chmod(desktop_entry_path, 0o755)