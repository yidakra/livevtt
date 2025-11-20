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
        if ((requestPath.equals("/livevtt/captions") || requestPath.equals("livevtt/captions")) &&
            ("POST".equalsIgnoreCase(requestMethod) || "PUT".equalsIgnoreCase(requestMethod))) {

            logger.info("LiveVTTCaptionHTTPProvider: *** PROCESSING CAPTION REQUEST ***");

            try {
                // Read request body
                logger.info("LiveVTTCaptionHTTPProvider: Reading request body...");
                InputStream is = req.getInputStream();
                StringBuilder bodyBuilder = new StringBuilder();
                byte[] buffer = new byte[1024];
                int bytesRead;
                while ((bytesRead = is.read(buffer)) != -1) {
                    bodyBuilder.append(new String(buffer, 0, bytesRead));
                }
                String requestBody = bodyBuilder.toString();

                logger.info("LiveVTTCaptionHTTPProvider: Request body: '" + requestBody + "'");

                // Extract fields from JSON (simplified parsing)
                logger.info("LiveVTTCaptionHTTPProvider: Parsing JSON...");
                Map<String, String> fields = parseJson(requestBody);

                logger.info("LiveVTTCaptionHTTPProvider: Parsed fields: " + (fields != null ? fields.toString() : "null"));

                if (fields == null) {
                    logger.warn("LiveVTTCaptionHTTPProvider: Fields is null - JSON parsing failed");
                    sendErrorResponse(resp, 400, "Invalid JSON");
                    return;
                }

                if (!fields.containsKey("text")) {
                    logger.warn("LiveVTTCaptionHTTPProvider: Missing text field. Available fields: " + fields.keySet());
                    sendErrorResponse(resp, 400, "Missing required field: text");
                    return;
                }

                if (!fields.containsKey("streamname")) {
                    logger.warn("LiveVTTCaptionHTTPProvider: Missing streamname field. Available fields: " + fields.keySet());
                    sendErrorResponse(resp, 400, "Missing required field: streamname");
                    return;
                }

                String text = fields.get("text");
                String streamName = fields.get("streamname");
                String language = fields.getOrDefault("lang", fields.getOrDefault("language", "eng"));
                int trackId = 99;
                try {
                    if (fields.containsKey("trackid")) {
                        trackId = Integer.parseInt(fields.get("trackid"));
                    } else if (fields.containsKey("trackId")) {
                        trackId = Integer.parseInt(fields.get("trackId"));
                    }
                } catch (NumberFormatException e) {
                    logger.warn("LiveVTTCaptionHTTPProvider: Invalid trackid, using default 99");
                }

                logger.info("LiveVTTCaptionHTTPProvider: Extracted data - text: '" + text + "', streamName: '" + streamName + "', language: '" + language + "', trackId: " + trackId);

                // Find application with specified stream
                boolean captionSent = false;

                logger.info("LiveVTTCaptionHTTPProvider: === SEARCHING FOR STREAM ===");
                logger.info("LiveVTTCaptionHTTPProvider: Target stream name: '" + streamName + "'");

                try {
                    // First try the most common case: live/_definst_
                    logger.info("LiveVTTCaptionHTTPProvider: Getting 'live' application...");
                    IApplication liveApp = vhost.getApplication("live");
                    if (liveApp != null) {
                        logger.info("LiveVTTCaptionHTTPProvider: Got 'live' application, getting '_definst_' instance...");
                        IApplicationInstance defInst = liveApp.getAppInstance("_definst_");
                        if (defInst != null) {
                            logger.info("LiveVTTCaptionHTTPProvider: Got '_definst_' instance, looking for stream: " + streamName);
                            IMediaStream stream = defInst.getStreams().getStream(streamName);
                                if (stream != null) {
                                logger.info("LiveVTTCaptionHTTPProvider: *** FOUND STREAM *** " + streamName + " in live/_definst_");
                                logger.info("LiveVTTCaptionHTTPProvider: Stream type: " + stream.getClass().getSimpleName());
                                logger.info("LiveVTTCaptionHTTPProvider: Stream isPublishStreamReady: " + stream.isPublishStreamReady(false, false));

                                    // Create caption data
                                    AMFDataObj captionData = new AMFDataObj();
                                    captionData.put("text", new AMFDataItem(text));
                                captionData.put("lang", new AMFDataItem(language));
                                    captionData.put("trackid", new AMFDataItem(trackId));

                                logger.info("LiveVTTCaptionHTTPProvider: Created AMF data, sending to stream...");

                                try {
                                    // Send caption to stream
                                    stream.sendDirect("onTextData", captionData);
                                    logger.info("LiveVTTCaptionHTTPProvider: *** SUCCESS *** Caption sent to " + streamName + ": " + text);
                                    captionSent = true;
                                } catch (Exception e) {
                                    logger.error("LiveVTTCaptionHTTPProvider: Error sending caption to stream: " + e.getMessage(), e);
                                }
                            } else {
                                logger.info("LiveVTTCaptionHTTPProvider: Stream '" + streamName + "' not found in live/_definst_");
                            }
                        } else {
                            logger.warn("LiveVTTCaptionHTTPProvider: _definst_ not found in live application");
                        }
                    } else {
                        logger.warn("LiveVTTCaptionHTTPProvider: live application not found");
                    }

                } catch (Exception e) {
                    logger.error("LiveVTTCaptionHTTPProvider: Exception during stream search: " + e.getMessage(), e);
                }

                logger.info("LiveVTTCaptionHTTPProvider: === SEARCH COMPLETE === Result: " + (captionSent ? "SUCCESS" : "NOT FOUND"));

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
        logger.info("LiveVTTCaptionHTTPProvider: Unknown request: " + requestMethod + " " + requestPath);
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

                        // Normalise legacy key name
                        if ("language".equalsIgnoreCase(key)) {
                            key = "lang";
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
