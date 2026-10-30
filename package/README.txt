AAC/M4A Encoder (FDK) for AIMP 6 on Linux

This add-on lets the AIMP converter write AAC audio to .m4a files. The converter runs fdkaac-aimp, which starts fdkaac 1.0.9 with the Fraunhofer FDK AAC library (libfdk-aac 3.0.0) linked in.

The converter gets three encoders, each with a CBR preset and a VBR preset:
- AAC-LC: 8000 to 96000 Hz, mono, stereo, 5.1 and 7.1
- HE-AAC: 16000 to 48000 Hz, mono and stereo
- HE-AAC v2: 16000 to 48000 Hz, stereo
The converter brings a source with another sample rate to the nearest rate in the list.

Requirements
AIMP 6 for Linux on x86-64.

Installation
Open enc_fdkaac.aimppack with AIMP and confirm the installation. AIMP restarts.

Removal
In Preferences, Plugins, uncheck the add-on and restart the converter. Remove is then enabled and removes the add-on.

File modes
The AIMP installer gives the programs of an add-on mode 0777. At its first conversion the add-on sets mode 0755 on fdkaac-aimp and fdkaac.

Licenses
LICENSE.fdkaac.txt holds the license of fdkaac, and LICENSE.fdk-aac.txt holds the license of libfdk-aac. The source code of this package is published at SOURCE-ARCHIVE-PLACE.
