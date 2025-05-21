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

## Step 4: Configure the HTTP Provider

1.  **Locate `VHost.xml`:**
    *   This file is usually located in the main Wowza configuration directory.
    *   Path: `[wowza-install-dir]/conf/VHost.xml`

2.  **Edit `VHost.xml`:**
    *   Open the file in a text editor.
    *   Find the `<HTTPProviders>` section.
    *   Add the following `<HTTPProvider>` entry **inside** the `<HTTPProviders>` section:
        ```xml
        <HTTPProvider>
            <BaseClass>com.livevtt.wowza.LiveVTTCaptionHTTPProvider</BaseClass>
            <RequestFilters>livevtt/captions*</RequestFilters> <!-- This ensures the provider handles requests to /livevtt/captions -->
            <AuthenticationMethod>none</AuthenticationMethod> <!-- For production, consider 'admin-digest' or other methods -->
        </HTTPProvider>
        ```
    *   Save the `VHost.xml` file.

## Step 5: Restart Wowza Streaming Engine

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

## Step 6: Verify the Installation

1.  **Check Wowza Logs:**
    *   Monitor the Wowza logs for any errors during startup and module loading.
    *   Log file path: `[wowza-install-dir]/logs/wowzastreamingengine_access.log` (and `wowzastreamingengine_error.log`).
    *   Look for lines similar to:
        ```
        INFO server comment - LiveVTTCaptionModule.onAppStart: Application: live/_definst_
        INFO server comment - LiveVTTCaptionHTTPProvider.onHTTPRequest: uri:/livevtt/captions/status
        ```
    *   Successful loading messages for `LiveVTTCaptionModule` and `LiveVTTCaptionHTTPProvider` should appear.

2.  **Test HTTP Provider Status Endpoint:**
    *   Open a web browser or use `curl` to access the status endpoint:
        ```bash
        curl "http://[your-wowza-server-ip]:8087/livevtt/captions/status"
        ```
    *   You should receive a JSON response indicating the module is running, for example:
        ```json
        {"module":"LiveVTTCaptionModule","version":"1.0.0","status":"running","captionsReceived":0}
        ```

3.  **Test Sending a Caption (Optional, but recommended):**
    *   Use `curl` to send a test caption. Replace `[your-wowza-server-ip]` and `yourStreamName` accordingly.
        ```bash
        curl -X POST -H "Content-Type: application/json" \
             -d '{"text":"Hello Wowza from LiveVTT!","language":"eng","trackId":99}' \
             "http://[your-wowza-server-ip]:8087/livevtt/captions?streamname=yourStreamName"
        ```
    *   You should receive a JSON success response:
        ```json
        {"status":"success","message":"Caption received and processed","captionId":1}
        ```
    *   If you have a stream named `yourStreamName` running and a player connected, you might see this caption.

4.  **Use `check_wowza.py` Script (from the LiveVTT project):**
    *   This script provides a more comprehensive check.
    *   Ensure the script is executable and run:
        ```bash
        python check_wowza.py -u http://[your-wowza-server-ip]:8087
        ```
    *   Review the output for any failures.

## Step 7: Testing with Mock Wowza Server

Before deploying to a production Wowza server, you can test the LiveVTT caption functionality using the included mock server:

1. **Start the mock Wowza server:**
   ```bash
   python mock_wowza.py
   ```
   This starts a server on `http://localhost:8087` that simulates the Wowza caption API.

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
   python test_wowza_api.py -u http://localhost:8087
   ```
   This sends test captions directly to the mock server.

For more detailed testing instructions, see the `TESTING.md` file.

## Step 8: Configure LiveVTT to Send Captions to Wowza

1.  **Run the LiveVTT `main.py` script with the `-rtmp` option:**
    ```bash
    python main.py -u <HLS_STREAM_URL> -la <LANGUAGE_CODE> --rtmp rtmp://[your-wowza-server-ip]/[application-name]/[stream-name]
    ```
    *   Example:
        ```bash
        python main.py -u https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8 -la ru -bt -rtmp rtmp://localhost/live/myStream
        ```
    *   Replace `[your-wowza-server-ip]`, `[application-name]` (e.g., `live`), and `[stream-name]` (e.g., `myStream`) with your actual Wowza RTMP stream details.

2.  **Verify captions in your player:**
    *   Connect a player that supports CEA-608/708 closed captions (e.g., JW Player, THEOplayer, VLC) to your Wowza RTMP stream.
    *   You should see the captions generated by LiveVTT appearing in the player.

## Troubleshooting

*   **Module Not Loading:**
    *   Double-check all paths in `Application.xml` and `VHost.xml`.
    *   Ensure the class names (`com.livevtt.wowza.LiveVTTCaptionModule`, `com.livevtt.wowza.LiveVTTCaptionHTTPProvider`) are correct.
    *   Verify the JAR file is in `[wowza-install-dir]/lib/` and has correct permissions.
    *   Check Wowza logs for detailed Java exceptions.
*   **HTTP Provider Not Responding (404 Error):**
    *   Ensure the `<RequestFilters>livevtt/captions*</RequestFilters>` in `VHost.xml` is correct.
    *   Verify Wowza's HTTP server is running on port 8087 (or the port configured in `VHost.xml`).
*   **Captions Not Appearing in Player:**
    *   Enable debug logging in the module by setting `livevtt.caption.debug` to `true` in `Application.xml` (and restart Wowza). Check Wowza logs for caption processing messages.
    *   Confirm the `streamname` parameter in the HTTP POST request from LiveVTT matches an active stream in Wowza.
    *   Ensure your player is configured to display closed captions and supports the format (CEA-608/708 over RTMP).
    *   Check LiveVTT logs (`main.py` output) for errors when sending captions.

## Security Considerations

For production deployments, it's important to secure the HTTP provider:

1. **Enable authentication:**
   Change the `<AuthenticationMethod>none</AuthenticationMethod>` in `VHost.xml` to:
   ```xml
   <AuthenticationMethod>admin-digest</AuthenticationMethod>
   ```

2. **Implement authentication in the HTTP provider:**
   Modify the `doHTTPAuthentication` method in `LiveVTTCaptionHTTPProvider.java`:
   ```java
   public boolean doHTTPAuthentication(IVHost vhost, IHTTPRequest req, IHTTPResponse resp)
   {
       // Get authentication info from request
       String authHeader = req.getHeader("Authorization");
       if (authHeader == null || !isValidAuth(authHeader)) {
           // Send authentication challenge
           resp.setHeader("WWW-Authenticate", "Digest realm=\"WowzaStreamingEngine\", nonce=\"" + generateNonce() + "\"");
           resp.setResponseCode(401);
           return false;
       }
       return true;
   }
   
   private boolean isValidAuth(String authHeader) {
       // Implement your authentication logic here
       // For example, check against configured credentials
       return true; // Replace with actual validation
   }
   
   private String generateNonce() {
       // Generate a secure nonce
       return Long.toString(System.currentTimeMillis());
   }
   ```

3. **Use HTTPS:**
   Configure Wowza to use HTTPS for the management interface. See the [Wowza documentation on SSL/TLS](https://www.wowza.com/docs/how-to-secure-wowza-streaming-engine-using-ssl-certificates) for details.

4. **Restrict IP access:**
   Consider configuring firewall rules to restrict access to port 8087 to only the servers running LiveVTT.

For more detailed security information, refer to the [Wowza Streaming Engine Security Guide](https://www.wowza.com/docs/how-to-secure-wowza-streaming-engine).

This comprehensive guide should assist you in setting up the LiveVTT captioning module with Wowza Streaming Engine. 