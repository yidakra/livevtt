package com.livevtt.wowza;

import java.io.*;
import java.util.*;

import com.wowza.util.*;
import com.wowza.wms.amf.*;
import com.wowza.wms.application.*;
import com.wowza.wms.logging.*;
import com.wowza.wms.media.model.*;
import com.wowza.wms.module.*;
import com.wowza.wms.stream.*;

/**
 * LiveVTT Caption Module for Wowza Streaming Engine
 * 
 * This module provides real-time closed caption support for Wowza Streaming Engine
 * by injecting onTextData events into live streams. It is designed to work with
 * the LiveVTT application to provide captions from transcribed audio.
 */
public class LiveVTTCaptionModule extends ModuleBase {
    
    // Logger
    private static final Class<?> CLASS = LiveVTTCaptionModule.class;
    private WMSLogger logger = WMSLoggerFactory.getLogger(CLASS);
    
    // Configuration
    private String defaultLanguage = "eng";
    private int defaultTrackId = 99;
    private boolean debugLogging = false;
    
    // Stream listeners map
    private Map<String, CaptionStreamListener> streamListeners = new HashMap<>();
    
    /**
     * Class to store caption data
     */
    public static class CaptionData {
        private String text;
        private String language;
        private int trackId;
        private long timestamp;
        
        public CaptionData(String text, String language, int trackId) {
            this.text = text;
            this.language = language;
            this.trackId = trackId;
            this.timestamp = System.currentTimeMillis();
        }
        
        public String getText() {
            return text;
        }
        
        public String getLanguage() {
            return language;
        }
        
        public int getTrackId() {
            return trackId;
        }
        
        public long getTimestamp() {
            return timestamp;
        }
    }
    
    /**
     * Stream listener to handle caption publishing
     */
    public class CaptionStreamListener implements IMediaStreamActionNotify3 {
        private IMediaStream stream;
        private Queue<CaptionData> captionQueue = new LinkedList<>();
        private Object queueLock = new Object();
        private boolean isRunning = false;
        private Thread captionThread;
        
        public CaptionStreamListener(IMediaStream stream) {
            this.stream = stream;
        }
        
        public void start() {
            if (isRunning) return;
            
            isRunning = true;
            captionThread = new Thread(new Runnable() {
                @Override
                public void run() {
                    processCaptionQueue();
                }
            });
            captionThread.setName("LiveVTTCaptionPublisher-" + stream.getName());
            captionThread.setDaemon(true);
            captionThread.start();
            
            if (debugLogging) {
                logger.info("LiveVTTCaptionModule: Started caption thread for stream: " + stream.getName());
            }
        }
        
        public void stop() {
            isRunning = false;
            if (captionThread != null) {
                captionThread.interrupt();
                captionThread = null;
            }
            
            synchronized (queueLock) {
                captionQueue.clear();
            }
            
            if (debugLogging) {
                logger.info("LiveVTTCaptionModule: Stopped caption thread for stream: " + stream.getName());
            }
        }
        
        public void addCaptionData(CaptionData captionData) {
            synchronized (queueLock) {
                captionQueue.add(captionData);
                queueLock.notify();
            }
        }
        
        private void processCaptionQueue() {
            while (isRunning) {
                CaptionData captionData = null;
                
                synchronized (queueLock) {
                    if (captionQueue.isEmpty()) {
                        try {
                            queueLock.wait();
                        } catch (InterruptedException e) {
                            break;
                        }
                    }
                    
                    if (!captionQueue.isEmpty()) {
                        captionData = captionQueue.poll();
                    }
                }
                
                if (captionData != null) {
                    sendCaptionData(captionData);
                }
            }
        }
        
        private void sendCaptionData(CaptionData captionData) {
            try {
                if (stream != null && stream.isPublishStreamReady(true, true)) {
                    AMFDataObj amfData = new AMFDataObj();
                    amfData.put("text", new AMFDataItem(captionData.getText()));
                    amfData.put("language", new AMFDataItem(captionData.getLanguage()));
                    amfData.put("trackid", new AMFDataItem(captionData.getTrackId()));
                    
                    stream.sendDirect("onTextData", amfData);
                    ((MediaStream)stream).processSendDirectMessages();
                    
                    if (debugLogging) {
                        logger.info("LiveVTTCaptionModule: Sent caption to stream " + stream.getName() + 
                                   ": [" + captionData.getLanguage() + "] " + captionData.getText());
                    }
                }
            } catch (Exception e) {
                logger.error("LiveVTTCaptionModule: Error sending caption data: " + e.getMessage(), e);
            }
        }
        
        // IMediaStreamActionNotify3 implementation
        @Override
        public void onPublish(IMediaStream stream, String streamName, boolean isRecord, boolean isAppend) {
            start();
        }

        @Override
        public void onUnPublish(IMediaStream stream, String streamName, boolean isRecord, boolean isAppend) {
            stop();
        }

        @Override
        public void onMetaData(IMediaStream stream, AMFPacket metaDataPacket) {
            // Not used
        }

        @Override
        public void onPauseRaw(IMediaStream stream, boolean isPause, double location) {
            // Not used
        }

        @Override
        public void onPause(IMediaStream stream, boolean isPause, double location) {
            // Not used
        }

        @Override
        public void onPlay(IMediaStream stream, String streamName, double playStart, double playLen, int playReset) {
            // Not used
        }

        @Override
        public void onSeek(IMediaStream stream, double location) {
            // Not used
        }

        @Override
        public void onStop(IMediaStream stream) {
            // Not used
        }

        @Override
        public void onCodecInfoVideo(IMediaStream stream, MediaCodecInfoVideo codecInfoVideo) {
            // Not used
        }

        @Override
        public void onCodecInfoAudio(IMediaStream stream, MediaCodecInfoAudio codecInfoAudio) {
            // Not used
        }
    }
    
    /**
     * Module initialization when application starts
     */
    public void onAppStart(IApplicationInstance appInstance) {
        // Load configuration from appInstance
        defaultLanguage = appInstance.getProperties().getPropertyStr("livevtt.caption.language", defaultLanguage);
        defaultTrackId = appInstance.getProperties().getPropertyInt("livevtt.caption.trackId", defaultTrackId);
        debugLogging = appInstance.getProperties().getPropertyBoolean("livevtt.caption.debug", debugLogging);
        
        logger.info("LiveVTTCaptionModule.onAppStart: Application: " + appInstance.getApplication().getName() + "/" + appInstance.getName());
        logger.info("LiveVTTCaptionModule: Initialized with language=" + defaultLanguage + ", trackId=" + defaultTrackId);
    }
    
    /**
     * Called when application instance is shut down
     */
    public void onAppStop(IApplicationInstance appInstance) {
        // Clean up any resources
        synchronized (streamListeners) {
        for (CaptionStreamListener listener : streamListeners.values()) {
            listener.stop();
        }
        streamListeners.clear();
        }
        
        logger.info("LiveVTTCaptionModule.onAppStop: Application: " + appInstance.getApplication().getName() + "/" + appInstance.getName());
    }
    
    /**
     * Called when a new stream is created
     */
    public void onStreamCreate(IMediaStream stream) {
        if (stream.isPublishStreamReady(true, true) && !stream.isTranscodeResult()) {
            CaptionStreamListener listener = new CaptionStreamListener(stream);
            streamListeners.put(stream.getName(), listener);
            stream.addClientListener(listener);
            
            if (debugLogging) {
                logger.info("LiveVTTCaptionModule: Added listener to stream: " + stream.getName());
            }
        }
    }
    
    /**
     * Called when a stream is destroyed
     */
    public void onStreamDestroy(IMediaStream stream) {
        CaptionStreamListener listener = streamListeners.remove(stream.getName());
        if (listener != null) {
            listener.stop();
            stream.removeClientListener(listener);
            
            if (debugLogging) {
                logger.info("LiveVTTCaptionModule: Removed listener from stream: " + stream.getName());
            }
        }
    }
    
    /**
     * Public API to add caption data to a stream
     * 
     * @param streamName The name of the stream to add captions to
     * @param text The caption text
     * @param language The caption language (ISO 639 code)
     * @param trackId The caption track ID
     * @return true if caption was added to queue, false otherwise
     */
    public boolean addCaptionToStream(String streamName, String text, String language, Integer trackId) {
        if (streamName == null || text == null) {
            return false;
        }
        
        CaptionStreamListener listener = streamListeners.get(streamName);
        if (listener != null) {
            // Use default values if not provided
            String captionLanguage = (language != null) ? language : defaultLanguage;
            int captionTrackId = (trackId != null) ? trackId : defaultTrackId;
            
            CaptionData captionData = new CaptionData(text, captionLanguage, captionTrackId);
            listener.addCaptionData(captionData);
            return true;
        }
        
        return false;
    }
    
    /**
     * Simplified version of addCaptionToStream using default language and track ID
     */
    public boolean addCaptionToStream(String streamName, String text) {
        return addCaptionToStream(streamName, text, null, null);
    }
} 