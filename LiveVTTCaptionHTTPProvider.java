package com.livevtt.wowza;

import java.io.*;
import java.util.*;

import com.wowza.wms.application.*;
import com.wowza.wms.http.*;
import com.wowza.wms.logging.*;
import com.wowza.wms.vhost.*;

/**
 * HTTP Provider for LiveVTT Caption Module
 * 
 * This provider allows sending captions to the LiveVTTCaptionModule via HTTP requests.
 * It provides a REST-like interface to add captions to streams.
 * 
 * Example usage:
 * POST /livevtt/captions?streamname=myStream
 * Content-Type: application/json
 * 
 * {
 *   "text": "This is a caption",
 *   "language": "eng",
 *   "trackId": 99
 * }
 */
public class LiveVTTCaptionHTTPProvider extends HTTProvider2Base {
    
    // Logger
    private static final Class<?> CLASS = LiveVTTCaptionHTTPProvider.class;
    private WMSLogger logger = WMSLoggerFactory.getLogger(CLASS);
    
    // Configuration
    private boolean debugLogging = false;
    
    @Override
    public void onHTTPRequest(IVHost vhost, IHTTPRequest req, IHTTPResponse resp) {
        if (!doHTTPAuthentication(vhost, req, resp)) {
            return;
        }
        
        String queryStr = req.getQueryString();
        String requestPath = req.getPath();
        String requestMethod = req.getMethod();
        
        if (debugLogging) {
            logger.info("LiveVTTCaptionHTTPProvider: " + requestMethod + " " + requestPath + 
                       (queryStr != null ? "?" + queryStr : ""));
        }
        
        // Only handle POST requests to /livevtt/captions
        if (!"POST".equalsIgnoreCase(requestMethod) || !requestPath.endsWith("/livevtt/captions")) {
            sendError(resp, 404, "Not Found");
            return;
        }
        
        // Parse query parameters
        Map<String, String> queryParams = parseQueryString(queryStr);
        String streamName = queryParams.get("streamname");
        
        if (streamName == null || streamName.isEmpty()) {
            sendError(resp, 400, "Missing required parameter: streamname");
            return;
        }
        
        try {
            // Read request body
            byte[] buffer = new byte[req.getContentLength()];
            req.getInputStream().read(buffer);
            String requestBody = new String(buffer, "UTF-8");
            
            if (debugLogging) {
                logger.info("LiveVTTCaptionHTTPProvider: Request body: " + requestBody);
            }
            
            // Parse JSON request body
            Map<String, Object> jsonData = parseJsonBody(requestBody);
            
            if (jsonData == null || !jsonData.containsKey("text")) {
                sendError(resp, 400, "Invalid request body. Missing required field: text");
                return;
            }
            
            String text = (String) jsonData.get("text");
            String language = (String) jsonData.getOrDefault("language", null);
            Integer trackId = null;
            
            if (jsonData.containsKey("trackId")) {
                try {
                    trackId = Integer.parseInt(jsonData.get("trackId").toString());
                } catch (NumberFormatException e) {
                    sendError(resp, 400, "Invalid trackId format. Must be an integer.");
                    return;
                }
            }
            
            // Find the LiveVTTCaptionModule in the application
            IApplication app = vhost.getApplication("live"); // Default to "live" application
            if (app == null) {
                // Try to find any application that has our module
                List<String> appNames = vhost.getApplicationNames();
                for (Object appNameObj : appNames) {
                    String appName = appNameObj.toString();
                    IApplication testApp = vhost.getApplication(appName);
                    if (testApp != null && testApp.getAppInstance("_definst_") != null) {
                        app = testApp;
                        break;
                    }
                }
            }
            
            if (app == null) {
                sendError(resp, 500, "No suitable application found");
                return;
            }
            
            // Get the default instance
            IApplicationInstance appInstance = app.getAppInstance("_definst_");
            if (appInstance == null) {
                sendError(resp, 500, "Application instance not found");
                return;
            }
            
            // Find our module
            LiveVTTCaptionModule module = (LiveVTTCaptionModule) appInstance.getModuleList().getModuleByName("LiveVTTCaptionModule");
            if (module == null) {
                sendError(resp, 500, "LiveVTTCaptionModule not found in application");
                return;
            }
            
            // Add the caption to the stream
            boolean success = module.addCaptionToStream(streamName, text, language, trackId);
            
            if (success) {
                // Return success response
                sendResponse(resp, 200, "Caption added successfully");
            } else {
                sendError(resp, 404, "Stream not found: " + streamName);
            }
            
        } catch (Exception e) {
            logger.error("LiveVTTCaptionHTTPProvider: Error processing request: " + e.getMessage(), e);
            sendError(resp, 500, "Internal Server Error: " + e.getMessage());
        }
    }
    
    /**
     * Parse query string into a map of parameters
     */
    private Map<String, String> parseQueryString(String queryString) {
        Map<String, String> params = new HashMap<>();
        
        if (queryString == null || queryString.isEmpty()) {
            return params;
        }
        
        String[] pairs = queryString.split("&");
        for (String pair : pairs) {
            int idx = pair.indexOf("=");
            if (idx > 0) {
                String key = pair.substring(0, idx);
                String value = pair.substring(idx + 1);
                params.put(key.toLowerCase(), value);
            }
        }
        
        return params;
    }
    
    /**
     * Parse JSON request body into a map
     */
    private Map<String, Object> parseJsonBody(String json) {
        Map<String, Object> result = new HashMap<>();
        
        if (json == null || json.isEmpty()) {
            return result;
        }
        
        // Very simple JSON parser - production code should use a proper JSON library
        json = json.trim();
        if (!json.startsWith("{") || !json.endsWith("}")) {
            return null;
        }
        
        // Remove the outer braces
        json = json.substring(1, json.length() - 1).trim();
        
        // Split by commas, but not commas inside quotes
        List<String> entries = new ArrayList<>();
        int start = 0;
        boolean inQuotes = false;
        for (int i = 0; i < json.length(); i++) {
            char c = json.charAt(i);
            if (c == '"') {
                inQuotes = !inQuotes;
            } else if (c == ',' && !inQuotes) {
                entries.add(json.substring(start, i).trim());
                start = i + 1;
            }
        }
        if (start < json.length()) {
            entries.add(json.substring(start).trim());
        }
        
        // Process each key-value pair
        for (String entry : entries) {
            int colonIdx = entry.indexOf(":");
            if (colonIdx > 0) {
                String key = entry.substring(0, colonIdx).trim();
                String value = entry.substring(colonIdx + 1).trim();
                
                // Remove quotes from key
                if (key.startsWith("\"") && key.endsWith("\"")) {
                    key = key.substring(1, key.length() - 1);
                }
                
                // Process value based on type
                if (value.startsWith("\"") && value.endsWith("\"")) {
                    // String value
                    value = value.substring(1, value.length() - 1);
                    result.put(key, value);
                } else if (value.equals("true") || value.equals("false")) {
                    // Boolean value
                    result.put(key, Boolean.parseBoolean(value));
                } else if (value.matches("-?\\d+(\\.\\d+)?")) {
                    // Numeric value
                    if (value.contains(".")) {
                        result.put(key, Double.parseDouble(value));
                    } else {
                        result.put(key, Integer.parseInt(value));
                    }
                } else if (value.equals("null")) {
                    // Null value
                    result.put(key, null);
                } else {
                    // Unknown type, store as string
                    result.put(key, value);
                }
            }
        }
        
        return result;
    }
    
    /**
     * Send an error response
     */
    private void sendError(IHTTPResponse resp, int statusCode, String message) {
        try {
            resp.setResponseCode(statusCode);
            resp.setHeader("Content-Type", "application/json");
            
            String jsonResponse = "{\"error\": \"" + message + "\"}";
            byte[] responseBytes = jsonResponse.getBytes();
            
            OutputStream output = resp.getOutputStream();
            output.write(responseBytes);
        } catch (Exception e) {
            logger.error("LiveVTTCaptionHTTPProvider: Error sending response: " + e.getMessage(), e);
        }
    }
    
    /**
     * Send a success response
     */
    private void sendResponse(IHTTPResponse resp, int statusCode, String message) {
        try {
            resp.setResponseCode(statusCode);
            resp.setHeader("Content-Type", "application/json");
            
            String jsonResponse = "{\"status\": \"success\", \"message\": \"" + message + "\"}";
            byte[] responseBytes = jsonResponse.getBytes();
            
            OutputStream output = resp.getOutputStream();
            output.write(responseBytes);
        } catch (Exception e) {
            logger.error("LiveVTTCaptionHTTPProvider: Error sending response: " + e.getMessage(), e);
        }
    }
    
    /**
     * Perform HTTP authentication if required
     */
    public boolean doHTTPAuthentication(IVHost vhost, IHTTPRequest req, IHTTPResponse resp) {
        // This can be expanded to include actual authentication logic
        return true;
    }
} 