package com.livevtt.wowza;

import java.io.*;
import java.util.*;

import com.wowza.wms.application.*;
import com.wowza.wms.http.*;
import com.wowza.wms.logging.*;
import com.wowza.wms.vhost.*;
import com.wowza.wms.stream.*;
import com.wowza.wms.amf.*;

/**
 * HTTP Provider for LiveVTT captions
 * 
 * This class handles HTTP requests to add captions to live streams
 */
public class LiveVTTCaptionHTTPProvider extends HTTProvider2Base {
    
    private static final Class<?> CLASS = LiveVTTCaptionHTTPProvider.class;
    private static final WMSLogger logger = WMSLoggerFactory.getLogger(CLASS);
    
    @Override
    public void onHTTPRequest(IVHost vhost, IHTTPRequest req, IHTTPResponse resp) {
        if (req == null || resp == null) {
            logger.error("LiveVTTCaptionHTTPProvider: Request or response is null");
            return;
        }

        String queryStr = req.getQueryString();
        String requestPath = req.getPath();
        String requestMethod = req.getMethod();
        
        logger.info("LiveVTTCaptionHTTPProvider: " + requestMethod + " " + requestPath + 
                    (queryStr != null ? "?" + queryStr : "") + " (HTTP Provider in use)");
        
        // Handle status request
        if (requestPath.endsWith("/livevtt/captions/status")) {
            try {
                StringBuilder sb = new StringBuilder();
                sb.append("{\"status\":\"active\",");
                sb.append("\"version\":\"1.0.0\",");
                sb.append("\"timestamp\":").append(System.currentTimeMillis()).append("}");
                
                sendResponse(resp, 200, sb.toString(), "application/json");
            } catch (Exception e) {
                logger.error("LiveVTTCaptionHTTPProvider: Error sending status: " + e.getMessage(), e);
                sendErrorResponse(resp, 500, "Internal Server Error");
            }
            return;
        }
        
        // Handle caption request
        if (requestPath.contains("/livevtt/captions") && 
            ("POST".equalsIgnoreCase(requestMethod) || "PUT".equalsIgnoreCase(requestMethod))) {
            
            try {
                // Read request body
                InputStream is = req.getInputStream();
                StringBuilder bodyBuilder = new StringBuilder();
                byte[] buffer = new byte[1024];
                int bytesRead;
                while ((bytesRead = is.read(buffer)) != -1) {
                    bodyBuilder.append(new String(buffer, 0, bytesRead));
                }
                String requestBody = bodyBuilder.toString();
                
                logger.info("LiveVTTCaptionHTTPProvider: Request body: " + requestBody);
                
                // Extract fields from JSON (simplified parsing)
                Map<String, String> fields = parseJson(requestBody);
                
                if (fields == null || !fields.containsKey("text")) {
                    sendErrorResponse(resp, 400, "Missing required field: text");
                    return;
                }
                
                if (!fields.containsKey("streamname")) {
                    sendErrorResponse(resp, 400, "Missing required field: streamname");
                    return;
                }
                
                String text = fields.get("text");
                String streamName = fields.get("streamname");
                String language = fields.getOrDefault("language", "eng");
                int trackId = 99;
                try {
                    if (fields.containsKey("trackId")) {
                        trackId = Integer.parseInt(fields.get("trackId"));
                    }
                } catch (NumberFormatException e) {
                    // Use default trackId
                }
                
                // Find application with specified stream
                boolean captionSent = false;
                
                // Try each application
                for (Object appNameObj : vhost.getApplicationNames()) {
                    String appName = appNameObj.toString();
                    IApplication app = vhost.getApplication(appName);
                    if (app != null) {
                        for (String instanceName : app.getAppInstanceNames()) {
                            IApplicationInstance appInstance = app.getAppInstance(instanceName);
                            if (appInstance != null) {
                                // Try to find the stream
                                IMediaStream stream = appInstance.getStreams().getStream(streamName);
                                if (stream != null) {
                                    logger.info("LiveVTTCaptionHTTPProvider: Found stream in " + 
                                              appName + "/" + instanceName);
                                    
                                    // Create caption data
                                    AMFDataObj captionData = new AMFDataObj();
                                    captionData.put("text", new AMFDataItem(text));
                                    captionData.put("language", new AMFDataItem(language));
                                    captionData.put("trackid", new AMFDataItem(trackId));
                                    
                                    // Send caption to stream
                                    stream.sendDirect("onTextData", captionData);
                                    logger.info("LiveVTTCaptionHTTPProvider: Sent caption to stream " + streamName);
                                    captionSent = true;
                                    break;
                                }
                            }
                        }
                    }
                    
                    if (captionSent) break;
                }
                
                if (captionSent) {
                    sendResponse(resp, 200, "{\"success\":true,\"message\":\"Caption added successfully\"}", "application/json");
                } else {
                    sendErrorResponse(resp, 404, "Stream not found: " + streamName);
                }
                
            } catch (Exception e) {
                logger.error("LiveVTTCaptionHTTPProvider: Error processing caption request: " + e.getMessage(), e);
                sendErrorResponse(resp, 500, "Internal Server Error");
            }
            
            return;
        }
        
        // Handle unknown requests
        sendErrorResponse(resp, 404, "Not Found");
    }
    
    private Map<String, String> parseJson(String json) {
        if (json == null || json.isEmpty()) {
            return null;
        }
        
        Map<String, String> result = new HashMap<>();
        
        try {
            // Very basic JSON parser
            json = json.trim();
            if (json.startsWith("{") && json.endsWith("}")) {
                json = json.substring(1, json.length() - 1);
                
                // Split by commas, but not commas inside quotes
                StringBuilder sb = new StringBuilder();
                boolean inQuotes = false;
                List<String> fields = new ArrayList<>();
                
                for (char c : json.toCharArray()) {
                    if (c == '"') {
                        inQuotes = !inQuotes;
                        sb.append(c);
                    } else if (c == ',' && !inQuotes) {
                        fields.add(sb.toString().trim());
                        sb.setLength(0);
                    } else {
                        sb.append(c);
                    }
                }
                
                if (sb.length() > 0) {
                    fields.add(sb.toString().trim());
                }
                
                // Process each field
                for (String field : fields) {
                    String[] parts = field.split(":", 2);
                    if (parts.length == 2) {
                        String key = parts[0].trim();
                        String value = parts[1].trim();
                        
                        // Remove quotes from key
                        if (key.startsWith("\"") && key.endsWith("\"")) {
                            key = key.substring(1, key.length() - 1);
                        }
                        
                        // Remove quotes from value
                        if (value.startsWith("\"") && value.endsWith("\"")) {
                            value = value.substring(1, value.length() - 1);
                        }
                        
                        result.put(key, value);
                    }
                }
            }
        } catch (Exception e) {
            logger.error("LiveVTTCaptionHTTPProvider: Error parsing JSON: " + e.getMessage(), e);
            return null;
        }
        
        return result;
    }
    
    private void sendResponse(IHTTPResponse resp, int statusCode, String body, String contentType) {
        try {
            resp.setResponseCode(statusCode);
            resp.setHeader("Content-Type", contentType);
            resp.setHeader("Access-Control-Allow-Origin", "*");
            
            OutputStream os = resp.getOutputStream();
            os.write(body.getBytes("UTF-8"));
            os.close();
        } catch (Exception e) {
            logger.error("LiveVTTCaptionHTTPProvider: Error sending response: " + e.getMessage(), e);
        }
    }
    
    private void sendErrorResponse(IHTTPResponse resp, int statusCode, String message) {
        try {
            String jsonError = "{\"success\":false,\"message\":\"" + message + "\"}";
            sendResponse(resp, statusCode, jsonError, "application/json");
        } catch (Exception e) {
            logger.error("LiveVTTCaptionHTTPProvider: Error sending error response: " + e.getMessage(), e);
        }
    }
} 