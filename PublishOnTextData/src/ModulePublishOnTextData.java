package com.wowza.wms.plugin.closedcaption.test;

import java.io.*;
import java.util.*;

import com.wowza.util.*;
import com.wowza.wms.amf.*;
import com.wowza.wms.application.IApplicationInstance;
import com.wowza.wms.media.model.*;
import com.wowza.wms.module.ModuleBase;
import com.wowza.wms.stream.*;

public class ModulePublishOnTextData extends ModuleBase
{
	class OnTextData
	{
		String text = "";
		
		public OnTextData(String text)
		{
			this.text = text;
		}
	}
	
	class PublishThread extends Thread
	{
		private boolean running = true;
		private Object lock = new Object();
		private int interval = 500;
		private int publishInterval = 1000;
		private long lastSend = -1;
		private IApplicationInstance appInstance = null;
		private IMediaStream stream = null;
		private int count = 0;

		public void doStop()
		{
			synchronized(lock)
			{
				this.running = false;
			}
		}
		
		public PublishThread(IApplicationInstance appInstance, IMediaStream stream)
		{
			this.appInstance = appInstance;
			this.stream = stream;
		}
		
		public void run()
		{
			getLogger().info("ModulePublishOnTextData#PublishThread.run["+stream.getContextStr()+"]: START");
			
			int index = 0;
			
			while(true)
			{
				try
				{
					long currTime = System.currentTimeMillis();
					if (lastSend < 0 || (currTime - lastSend) > publishInterval)
					{
						lastSend = currTime;
						
						while(true)
						{
							if (onTextDataList.size() <= 0)
								break;
							
							OnTextData onTextData = onTextDataList.get(index%onTextDataList.size());
							index++;
							
							if (onTextData == null)
								break;
							
							sendTextDataMessage(stream, onTextData);
							break;
						}
					}
					
					Thread.sleep(interval);
				}
				catch(Exception e)
				{
					getLogger().error("ModulePublishOnTextData#PublishThread.run["+stream.getContextStr()+"]: "+e.toString());
				}
				
				synchronized(lock)
				{
					if (!running)
						break;
				}
			}
			getLogger().info("ModulePublishOnTextData#PublishThread.run["+stream.getContextStr()+"]: STOP");
		}

		public void sendTextDataMessage(IMediaStream stream, OnTextData onTextData)
		{
			try
			{
				AMFDataObj amfData = new AMFDataObj();

				//System.out.println("Text: "+count);

				//debug  amfData.put("text", new AMFDataItem("T: "+(count++)));
				amfData.put("text", new AMFDataItem(onTextData.text));
				amfData.put("language", new AMFDataItem(languageID));
				amfData.put("trackid", new AMFDataItem(trackNumber));							
				stream.sendDirect("onTextData", amfData);
				((MediaStream)stream).processSendDirectMessages();	
				
			

			}
			catch(Exception e)
			{
				getLogger().error("ModulePublishOnTextData#PublishThread.sendTextDataMessage["+stream.getContextStr()+"]: "+e.toString());
				e.printStackTrace();
			}
		}

		public int getPublishInterval()
		{
			return publishInterval;
		}

		public void setPublishInterval(int publishInterval)
		{
			this.publishInterval = publishInterval;
		}
	}

	public class MyMediaStreamListener implements IMediaStreamActionNotify3
	{
		private PublishThread publishThread = null;

		public void onPublish(IMediaStream stream, String streamName, boolean isRecord, boolean isAppend)
		{
			IApplicationInstance appInstance = stream.getStreams().getAppInstance();
			
			if (!stream.isTranscodeResult())
			{
				publishThread = new PublishThread(appInstance, stream);
				publishThread.setName("OnTextDataPublisher-"+appInstance.getContextStr()+"-"+streamName);
				publishThread.setDaemon(true);
				publishThread.setPublishInterval(publishInterval);
				publishThread.start();
			}
		}

		public void onUnPublish(IMediaStream stream, String streamName, boolean isRecord, boolean isAppend)
		{
			if (publishThread != null)
				publishThread.doStop();
			publishThread = null;
		}

		public void onMetaData(IMediaStream stream, AMFPacket metaDataPacket)
		{
		}

		public void onPauseRaw(IMediaStream stream, boolean isPause, double location)
		{
		}

		public void onPause(IMediaStream stream, boolean isPause, double location)
		{
		}

		public void onPlay(IMediaStream stream, String streamName, double playStart, double playLen, int playReset)
		{
		}

		public void onSeek(IMediaStream stream, double location)
		{
		}

		public void onStop(IMediaStream stream)
		{
		}

		public void onCodecInfoVideo(IMediaStream stream, MediaCodecInfoVideo codecInfoVideo)
		{
		}

		public void onCodecInfoAudio(IMediaStream stream, MediaCodecInfoAudio codecInfoAudio)
		{
		}
	}

	private List<OnTextData> onTextDataList = new ArrayList<OnTextData>();
	private boolean charsetTest = false;
	private String languageID = "eng";
	private int trackNumber = 99;
	//private final Charset UTF8_CHARSET = Charset.forName("UTF-8"); 
	private int publishInterval = 1000;
	
	public void onAppStart(IApplicationInstance appInstance)
	{
		getLogger().info("ModulePublishOnTextData.onAppStart["+appInstance.getContextStr()+"]");
		
		String onTextDataFile = "${com.wowza.wms.context.VHostConfigHome}/content/ontextdata.txt";

		publishInterval = appInstance.getProperties().getPropertyInt("publishOnTextDataPublishInterval", publishInterval);
		onTextDataFile = appInstance.getProperties().getPropertyStr("publishOnTextDataFile", onTextDataFile);
		languageID = appInstance.getProperties().getPropertyStr("publishOnTextDataLanguageID", languageID);
		trackNumber = appInstance.getProperties().getPropertyInt("publishOnTextDataTrackNumber", trackNumber);
		
		charsetTest = appInstance.getProperties().getPropertyBoolean("publishOnTextCharsetTest", charsetTest);

		Map<String, String> pathMap = new HashMap<String, String>();
		pathMap.put("com.wowza.wms.context.VHost", appInstance.getVHost().getName());
		pathMap.put("com.wowza.wms.context.VHostConfigHome", appInstance.getVHost().getHomePath());
		pathMap.put("com.wowza.wms.context.Application", appInstance.getApplication().getName());
		pathMap.put("com.wowza.wms.context.ApplicationInstance", appInstance.getName());
		
		onTextDataFile =  SystemUtils.expandEnvironmentVariables(onTextDataFile, pathMap);

		File file = new File(onTextDataFile);
		
		getLogger().info("ModulePublishOnTextData.onAppStart["+appInstance.getContextStr()+"]: sendInterval: "+publishInterval);
		
		if (charsetTest)
		{
			int charCode = 0x20;
			int lastChar = 0x100;
			int charsPerLine = 20;
			
			while(true)
			{
				int charsToPublish = lastChar-charCode;
				if (charsToPublish > charsPerLine)
					charsToPublish = charsPerLine;
								
				String bytesStr = "";
				for(int i=0;i<charsToPublish;i++)
				{
					int thisChar = charCode+i;
					
					// map unicode codepoint to utf-8
					int myChar = 0;
					if (thisChar >= 0x020 && thisChar < 0x080)
						myChar = (int)thisChar;
					else if (thisChar >= 0x080 && thisChar < 0x0C0)
						myChar = (int)(0x0c280 + (thisChar - 0x080));
					else if (thisChar >= 0x0C0 && thisChar < 0x100)
						myChar = (int)(0x0c380 + (thisChar - 0x0C0));

					try
					{
						bytesStr += new String(BufferUtils.intToByteArray(myChar, (myChar<0x080?1:2)), "UTF-8");
					}
					catch(Exception e)
					{
					}
				}
				
				bytesStr = "0x"+Integer.toHexString(charCode)+":"+bytesStr+":";
				
				onTextDataList.add(new OnTextData(bytesStr));
								
				charCode += charsToPublish;
				
				if (charCode >= lastChar)
					break;
			}
		}
		else
		{
			getLogger().info("ModulePublishOnTextData.onAppStart["+appInstance.getContextStr()+"]: onTextDataFile[exists:"+file.exists()+"]: "+onTextDataFile);

			BufferedReader inf = null;
			if (file.exists())
			{
				try
				{
					inf = new BufferedReader(new FileReader(file));
					String line;
					while ((line = inf.readLine()) != null)
					{
						line = line.trim();
						if (line.startsWith("#"))
							continue;
						if (line.length() == 0)
							continue;
											
						onTextDataList.add(new OnTextData(line));
						
					}
				}
				catch(Exception e)
				{
					getLogger().error("ModulePublishOnTextData.onAppStart[read]: "+ e.toString());
				}
			}
			
			getLogger().info("ModulePublishOnTextData.onAppStart["+appInstance.getContextStr()+"]: onTextDataFileCount: "+onTextDataList.size());

			try
			{
				if (inf != null)
					inf.close();
				inf = null;	
			}
			catch(Exception e)
			{
				getLogger().error("ModulePublishOnTextData.onAppStart[close]: "+ e.toString());
			}
		}
	}
	
	public void onStreamCreate(IMediaStream stream)
	{
		stream.addClientListener(new MyMediaStreamListener());
	}
}
