# LiveVTT Wowza Module Setup Guide

This guide provides step-by-step instructions for installing and configuring the LiveVTT Caption Module on Wowza Streaming Engine.

## Prerequisites

*   Wowza Streaming Engine installed and running.
*   Java Development Kit (JDK) 8 or higher installed on the machine where you will build the module.
*   Access to the Wowza server's file system and configuration files.
*   The LiveVTT project files, including the Java source files (`LiveVTTCaptionModule.java`, `LiveVTTCaptionHTTPProvider.java`) and the build script (`java_module_build.sh`).

### Verifying Prerequisites

Before proceeding, verify that your environment meets the requirements:

1. **Check Java version**:
   ```bash
   javac -version
   ```
   You should see output indicating Java 8 or higher (e.g., `javac 1.8.0_301` or `javac 11.0.12`).

2. **Verify Wowza installation**:
   Ensure Wowza Streaming Engine is installed and running:
   ```bash
   # Check if Wowza service is running (Linux/macOS)
   ps aux | grep WowzaStreamingEngine
   
   # Or check the status of the service
   sudo service WowzaStreamingEngine status
   ```

3. **Verify access to Wowza configuration files**:
   Make sure you have read/write access to the Wowza configuration directory.

## Step 1: Build the Java Module

1.  **Navigate to the LiveVTT project directory:**
    ```bash
    cd /path/to/livevtt
    ```

2.  **Ensure the build script is executable:**
    ```bash
    chmod +x java_module_build.sh
    ```

3.  **Modify the build script (if necessary):**
    *   Open `java_module_build.sh` in a text editor.
    *   Locate the `WOWZA_LIB_DIR` variable.
    *   Update its value to the correct path of your Wowza Streaming Engine's `lib` directory.
        *   Default on macOS: `/Library/WowzaStreamingEngine/lib`
        *   Default on Windows: `/Program Files (x86)/Wowza Media Systems/Wowza Streaming Engine/lib` 
          > **Note for Windows users**: In the script, use forward slashes (`/`) or escaped backslashes (`\\`) for paths. The example above uses forward slashes which work in bash environments like Git Bash or WSL.

        *   Default on Linux: `/usr/local/WowzaStreamingEngine/lib`

4.  **Run the build script:**
    ```bash
    ./java_module_build.sh
    ```
    This script will compile the Java files and create a JAR file named `livevtt-caption-module.jar` in a new `build` directory.

5.  **Verify build output:**
    *   Check that the `build` directory was created.
    *   Confirm that `build/livevtt-caption-module.jar` exists.
    *   If there are errors, ensure `WOWZA_LIB_DIR` is correct and that the JDK is properly installed and in your PATH.

## Step 2: Install the Module on Wowza Server

1.  **Copy the JAR file to Wowza's `lib` directory:**
    *   **If Wowza is on the same machine:**
        ```bash
        cp build/livevtt-caption-module.jar [wowza-install-dir]/lib/
        ```
        (Replace `[wowza-install-dir]` with the actual path to your Wowza installation.)
    *   **If Wowza is on a remote server:**
        Use `scp` or your preferred file transfer method:
        ```bash
        scp build/livevtt-caption-module.jar user@your-wowza-server-ip:[wowza-install-dir]/lib/
        ```

2.  **Verify file permissions (on the Wowza server):**
    Ensure the copied JAR file has appropriate read permissions for the Wowza process. Typically, this is handled correctly by default, but you can set it explicitly if needed:
    ```bash
    chmod 644 [wowza-install-dir]/lib/livevtt-caption-module.jar
    ```

## Step 3: Configure the Module in Wowza

1.  **Locate `Application.xml`:**
    *   This file is specific to the Wowza application you want to use with LiveVTT.
    *   Path: `[wowza-install-dir]/conf/[application-name]/Application.xml`
    *   For a typical live streaming application named `live`, the path would be: `[wowza-install-dir]/conf/live/Application.xml`

2.  **Edit `Application.xml`:**
    *   Open the file in a text editor.
    *   Find the `<Modules>` section.
    *   Add the following `<Module>` entry **inside** the `<Modules>` section:
        ```xml
        <Module>
            <Name>LiveVTTCaptionModule</Name>
            <Description>LiveVTT Caption Module for real-time closed captioning</Description>
            <Class>com.livevtt.wowza.LiveVTTCaptionModule</Class>
        </Module>
        ```
        > **Note**: Wowza uses `<Name>` tags in newer versions, but older versions might use `<n>` tags. Check your existing Application.xml file to see which format is used and adjust accordingly.

3.  **Add optional module properties (if needed):**
    *   These properties allow you to customize the module's behavior.
    *   Add them inside the `<Properties>` section of `Application.xml` (this section should be at the same level as `<Modules>`):
        ```xml
        <Property>
            <Name>livevtt.caption.language</Name>
            <Value>eng</Value>
            <Type>String</Type>
        </Property>
        <Property>
            <Name>livevtt.caption.trackId</Name>
            <Value>99</Value>
            <Type>Integer</Type>
        </Property>
        <Property>
            <Name>livevtt.caption.debug</Name>
            <Value>false</Value>
            <Type>Boolean</Type>
        </Property>
        ```
        > **Note**: Use the same tag format (`<Name>` or `<n>`) as your existing properties in the file.
    *   Save the `Application.xml` file.

## Step 4: Configure Application.xml for HLS WebVTT (Cupertino)

For HLS (Apple's HTTP Live Streaming) to properly include WebVTT subtitles, specific properties need to be configured in your application's `Application.xml` file (`[wowza-install-dir]/conf/[application-name]/Application.xml`).

1.  **Edit `Application.xml`:**
    *   Open the file for your streaming application (e.g., `[wowza-install-dir]/conf/live/Application.xml`).
    *   Locate the `<HTTPStreamers>` section. Ensure `cupertinostreaming` is listed.
        ```xml
        <HTTPStreamers>
            <HTTPStreamer>cupertinostreaming</HTTPStreamer>
            <HTTPStreamer>mpegdashstreaming</HTTPStreamer>
            <!-- other http streamers -->
        </HTTPStreamers>
        ```
    *   Locate the `<LiveStreamPacketizers>` section. Ensure `cupertinostreamingpacketizer` is listed.
        ```xml
        <LiveStreamPacketizers>
            <LiveStreamPacketizer>cupertinostreamingpacketizer</LiveStreamPacketizer>
            <LiveStreamPacketizer>mpegdashstreamingpacketizer</LiveStreamPacketizer>
            <!-- other packetizers -->
        </LiveStreamPacketizers>
        ```
    *   Find the main application-level `<Properties>` container (usually near the end of the file, a direct child of `<Application>`).
    *   Add or verify the following properties are present and correctly configured:
        ```xml
        <!-- Properties for HLS (Cupertino) WebVTT captions -->
        <Property>
            <Name>cupertinoCreateAudioOnlyRendition</Name>
            <Value>false</Value>
            <Type>Boolean</Type>
        </Property>
        <Property>
            <Name>cupertinoChunkDurationTarget</Name>
            <Value>10000</Value> <!-- e.g., 10 seconds -->
            <Type>Integer</Type>
        </Property>
        <Property>
            <Name>cupertinoMaxChunkCount</Name>
            <Value>10</Value>
            <Type>Integer</Type>
        </Property>
        <Property>
            <Name>cupertinoPlaylistChunkCount</Name>
            <Value>3</Value>
            <Type>Integer</Type>
        </Property>
        <Property>
            <Name>cupertinoRepeaterChunkCount</Name>
            <Value>3</Value>
            <Type>Integer</Type>
        </Property>
        <!-- Property to enable WebVTT captions for Cupertino -->
        <Property>
            <Name>cupertinoTagVTT</Name>
            <Value>true</Value>
            <Type>Boolean</Type>
        </Property>
        <!-- Property to set the caption language for WebVTT (use BCP-47 language tags) -->
        <Property>
            <Name>cupertinoTagVTTLanguage</Name>
            <Value>eng</Value> <!-- Example: English. Change as needed. -->
            <Type>String</Type>
        </Property>
        <!-- Property to specify how captions are ingested (onTextData for this module) -->
        <Property>
            <Name>captionLiveIngestType</Name>
            <Value>onTextData</Value>
            <Type>String</Type>
        </Property>
        ```
    *   Save the `Application.xml` file.

## Step 5: Configure the HTTP Provider in VHost.xml

1.  **Locate `VHost.xml`:**
    *   This file is usually located in the main Wowza configuration directory.
    *   Path: `[wowza-install-dir]/conf/VHost.xml`

2.  **Edit `VHost.xml`:**
    *   Open the file in a text editor.
    *   Find the `<HTTPProviders>` section within the `<HostPort>` that Wowza uses for administration and HTTP-based services (often port `8086` or `8087`. **For caption submission, LiveVTT defaults to port 8086**).
    *   Add the following `<HTTPProvider>` entry **inside** the relevant `<HTTPProviders>` section:
        ```xml
        <HTTPProvider>
            <BaseClass>com.livevtt.wowza.LiveVTTCaptionHTTPProvider</BaseClass>
            <RequestFilters>livevtt/captions*</RequestFilters> <!-- This ensures the provider handles requests to /livevtt/captions and /livevtt/captions/status -->
            <AuthenticationMethod>none</AuthenticationMethod> <!-- For initial testing. For production, consider 'admin-digest' or other secure methods -->
        </HTTPProvider>
        ```
    *   **Important:** Ensure that if `LiveVTTCaptionHTTPProvider` is already listed (e.g., under port 1935), it's also configured correctly for the port `main.py` will use (default 8086). The `RequestFilters` should be `livevtt/captions*` to handle both `/livevtt/captions` (for POSTing data) and `/livevtt/captions/status` (for GETting status).
    *   Save the `VHost.xml` file.

## Step 6: Restart Wowza Streaming Engine

For the changes to take effect, you must restart the Wowza Streaming Engine service.

*   **On Linux/macOS (using startup scripts):**
    ```bash
    sudo service WowzaStreamingEngine restart 
    # or
    sudo service WowzaStreamingEngineManager restart
    # or navigate to [wowza-install-dir]/bin/ and run:
    # sudo ./shutdown.sh
    # sudo ./startup.sh
    ```
*   **On Windows:**
    *   Use the Wowza Streaming Engine Manager application to stop and start the services.
    *   Alternatively, use the Windows Services console (`services.msc`).

## Step 7: Verify the Installation

1.  **Check Wowza Logs:**
    *   Monitor the Wowza logs for any errors during startup and module loading.
    *   Log file path: `[wowza-install-dir]/logs/wowzastreamingengine_access.log` (and `wowzastreamingengine_error.log`).
    *   Look for lines similar to:
        ```
        INFO server comment - LiveVTTCaptionModule.onAppStart: Application: live/_definst_
        INFO server comment - LiveVTTCaptionHTTPProvider: POST /livevtt/captions (HTTP Provider in use)
        INFO server comment - LiveVTTCaptionHTTPProvider: GET /livevtt/captions/status (HTTP Provider in use)
        ```
    *   Successful loading messages for `LiveVTTCaptionModule` and `LiveVTTCaptionHTTPProvider` should appear.

2.  **Test HTTP Provider Status Endpoint:**
    *   Open a web browser or use `curl` to access the status endpoint. Use the port configured in `VHost.xml` for the `LiveVTTCaptionHTTPProvider` (e.g., 8086 or 8087):
        ```bash
        curl "http://[your-wowza-server-ip]:8086/livevtt/captions/status"
        ```
    *   You should receive a JSON response indicating the module is running, for example:
        ```json
        {"status":"active","version":"1.0.0","timestamp":1678886400000}
        ```

3.  **Test Sending a Caption (Optional, but recommended):**
    *   Use `curl` to send a test caption. Replace `[your-wowza-server-ip]`, port (e.g. 8086), and `yourStreamName` accordingly.
        ```bash
        curl -X POST -H "Content-Type: application/json" \
             -d '{"text":"Hello Wowza from LiveVTT!","language":"eng","trackId":99, "streamname":"yourStreamName"}' \
             "http://[your-wowza-server-ip]:8086/livevtt/captions"
        ```
    *   You should receive a JSON success response:
        ```json
        {"success":true,"message":"Caption added successfully"}
        ```
    *   If you have a stream named `yourStreamName` running and a player connected, and `Application.xml` is set for WebVTT, you might see this caption in an HLS stream.

4.  **Use `check_wowza.py` Script (from the LiveVTT project):**
    *   This script provides a more comprehensive check.
    *   Ensure the script is executable and run, pointing it to the correct port (e.g., 8086 for the caption submission endpoint, or the port where the status endpoint is if different):
        ```bash
        python check_wowza.py -u http://[your-wowza-server-ip]:8086
        ```
    *   Review the output for any failures.

## Step 8: Testing with Mock Wowza Server

Before deploying to a production Wowza server, you can test the LiveVTT caption functionality using the included mock server:

1. **Start the mock Wowza server:**
   ```bash
   python mock_wowza.py
   ```
   This starts a server on `http://localhost:8086` that simulates the Wowza caption API.

2. **Test the LiveVTT integration:**
   ```bash
   python test_integration.py
   ```
   This script will:
   - Start the mock server
   - Run LiveVTT with the TVRain stream
   - Verify that captions are being sent correctly

3. **Test the API directly:**
   ```bash
   python test_wowza_api.py -u http://localhost:8086
   ```
   This sends test captions directly to the mock server.

For more detailed testing instructions, see the `TESTING.md` file.

## Step 9: Configure LiveVTT to Send Captions to Wowza

1.  **Run the LiveVTT `main.py` script with the `-rtmp` and `-rtmp-port` options:**
    ```bash
    python main.py -u <HLS_STREAM_URL> -la <LANGUAGE_CODE> --rtmp rtmp://[your-wowza-server-ip]/[application-name]/[stream-name] --rtmp-http-port 8086
    ```
    *   Example:
        ```bash
        python main.py -u https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8 -la ru -bt -rtmp rtmp://localhost/live/myStream --rtmp-http-port 8086
        ```
    *   Replace `[your-wowza-server-ip]`, `[application-name]` (e.g., `live`), and `[stream-name]` (e.g., `myStream`) with your actual Wowza RTMP stream details.
    *   Ensure `--rtmp-http-port` matches the port where `LiveVTTCaptionHTTPProvider` is configured in `VHost.xml` and active for caption submission.

2.  **Verify captions in your player:**
    *   Connect an HLS player (e.g., VLC, Safari, or a web-based HLS player) to your Wowza HLS stream URL (e.g., `http://[your-wowza-server-ip]:1935/[application-name]/[stream-name]/playlist.m3u8`).
    *   You should see the WebVTT captions generated by LiveVTT appearing in the player.

## Troubleshooting

*   **Module Not Loading:**
    *   Double-check all paths in `Application.xml` and `VHost.xml`.
    *   Ensure the class names (`com.livevtt.wowza.LiveVTTCaptionModule`, `com.livevtt.wowza.LiveVTTCaptionHTTPProvider`) are correct.
    *   Verify the JAR file is in `[wowza-install-dir]/lib/` and has correct permissions.
    *   Check Wowza logs for detailed Java exceptions or messages indicating the module or HTTP provider could not be loaded or initialized.
*   **HTTP Provider Not Responding (404 Error from LiveVTT `main.py`):**
    *   Ensure the `<RequestFilters>livevtt/captions*</RequestFilters>` in `VHost.xml` is correct for the HostPort that `main.py` is sending to (default 8086).
    *   The `LiveVTTCaptionHTTPProvider.java` should handle requests to `/livevtt/captions` (POST) and `/livevtt/captions/status` (GET).
    *   Verify Wowza's HTTP server is running on the configured port (e.g., 8086) and that no firewall is blocking access.
*   **Captions Not Appearing in HLS Player (but no 404 errors from `main.py`):**
    *   Double-check all `cupertino...` properties in `Application.xml` as listed in **Step 4**.
    *   Ensure `captionLiveIngestType` is set to `onTextData`.
    *   Verify that the `LiveStreamPacketizers` includes `cupertinostreamingpacketizer`.
    *   Enable debug logging in the Wowza module (`livevtt.caption.debug` to `true` in `Application.xml`, then restart Wowza). Check Wowza logs for messages from `LiveVTTCaptionModule` and `LiveVTTCaptionHTTPProvider`.
