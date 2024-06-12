import java.io.IOException;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public class AppSettings {
    public String colorHex;
    public String FontName;
    public String ImagesPath;
    public String DateFormat;
    public String TimeFormat;
    public int DelayBetweenImages;
    public int DefaultMaxFPS;
    public int DefaultAnimationDuration;
    public int DefaultVerticalImageEffect;

    public AppSettings() {
    }

    public String serialize() throws JsonProcessingException {
        ObjectMapper mapper = new ObjectMapper();
        return mapper.writeValueAsString(this);
    }

    public static AppSettings deserialize(String jsonString) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        return mapper.readValue(jsonString, AppSettings.class);
    }

}