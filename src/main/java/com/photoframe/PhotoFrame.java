package org.alws.photoframe;

import com.defano.jsegue.*;
import com.defano.jsegue.renderers.AlphaDissolveEffect;
import com.defano.jsegue.renderers.BarnDoorCloseEffect;
import com.defano.jsegue.renderers.BarnDoorOpenEffect;
import com.defano.jsegue.renderers.BlindsEffect;
import com.defano.jsegue.renderers.CheckerboardEffect;
import com.defano.jsegue.renderers.IrisCloseEffect;
import com.defano.jsegue.renderers.IrisOpenEffect;
import com.defano.jsegue.renderers.PixelDissolveEffect;
import com.defano.jsegue.renderers.ScrollDownEffect;
import com.defano.jsegue.renderers.ScrollLeftEffect;
import com.defano.jsegue.renderers.ScrollRightEffect;
import com.defano.jsegue.renderers.ScrollUpEffect;
import com.defano.jsegue.renderers.ShrinkToBottomEffect;
import com.defano.jsegue.renderers.ShrinkToCenterEffect;
import com.defano.jsegue.renderers.ShrinkToTopEffect;
import com.defano.jsegue.renderers.StretchFromBottomEffect;
import com.defano.jsegue.renderers.StretchFromCenterEffect;
import com.defano.jsegue.renderers.StretchFromTopEffect;
import com.defano.jsegue.renderers.WipeDownEffect;
import com.defano.jsegue.renderers.WipeLeftEffect;
import com.defano.jsegue.renderers.WipeRightEffect;
import com.defano.jsegue.renderers.WipeUpEffect;
import com.defano.jsegue.renderers.ZoomInEffect;
import com.defano.jsegue.renderers.ZoomOutEffect;

import java.awt.*;
import java.awt.event.*;
import java.awt.image.BufferedImage;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import javax.imageio.ImageIO;
import javax.swing.*;
import java.util.Random;

public class PhotoFrame extends JFrame implements SegueAnimationObserver {

    /**
     * 
     */
    private static final long serialVersionUID = 1L;
    private static long DEFAULT_ANIMATION_DURATION;
    private static int DEFAULT_SLEEP_DURATION;
    private static int DEFAULT_MAX_FPS;

    private static final int DEFAULT_MAX_ANIMATIONS = 24; // this is all the animation segue supports.

    private JPanel backPanel;
    private JLabel photoLabel;
    JLabel dateLabel = new JLabel();
    JLabel timeLabel = new JLabel();

    private List<String> photos;
    private AnimatedSegue currentSegue;
    private int screenWidth;
    private int screenHeight;
    private Timer timer;
    AppSettings appSettings = new AppSettings();
    private boolean m_isRunning = true;

    private boolean m_IsDebug = false;

    public PhotoFrame() {
        super("Photo Frame");
        setExtendedState(JFrame.MAXIMIZED_BOTH);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        if (!m_IsDebug)
            this.setUndecorated(true); // Remove window decorations

        String jsonString;
        String filePath = "./settings.json";

        if (m_IsDebug)
            filePath = "./src/main/java/org/alws/photoframe/settings.json";

        try {
            jsonString = readFile(filePath);

            if (jsonString == null) {
                System.out.println("Cant read json string from file");
                return;
            }
            appSettings = AppSettings.deserialize(jsonString);
        } catch (IOException e) {
            e.printStackTrace();
            m_isRunning = false;
            return;
        } // Replace with your reading method

        DEFAULT_ANIMATION_DURATION = appSettings.DefaultAnimationDuration;
        DEFAULT_SLEEP_DURATION = appSettings.DelayBetweenImages;
        DEFAULT_MAX_FPS = appSettings.DefaultMaxFPS;
        // Create and set up the back panel
        backPanel = new JPanel();
        SpringLayout springLayout = new SpringLayout();
        backPanel.setLayout(springLayout);

        Color foregroundColor = Color.decode(appSettings.colorHex);
        String fontName = appSettings.FontName;

        setScreenSize();

        // Create and set up the time label
        timeLabel = new JLabel();
        timeLabel.setFont(new Font(fontName, Font.BOLD, 120));
        timeLabel.setForeground(foregroundColor);

        // Position the time label in the bottom-left corner
        springLayout.putConstraint(SpringLayout.WEST, timeLabel, 10, SpringLayout.WEST, backPanel);
        springLayout.putConstraint(SpringLayout.SOUTH, timeLabel, -60, SpringLayout.SOUTH, backPanel);
        backPanel.add(timeLabel);

        // Create and set up the date label
        dateLabel = new JLabel();
        dateLabel.setFont(new Font(fontName, Font.BOLD, 60));
        dateLabel.setForeground(foregroundColor);

        // Position the date label in the bottom-left corner
        springLayout.putConstraint(SpringLayout.WEST, dateLabel, 60, SpringLayout.WEST, backPanel);
        springLayout.putConstraint(SpringLayout.SOUTH, dateLabel, -10, SpringLayout.SOUTH, backPanel);
        backPanel.add(dateLabel);

        // Create and set up the photo label
        photoLabel = new JLabel();
        photoLabel.setHorizontalAlignment(SwingConstants.CENTER);
        photoLabel.setVerticalAlignment(SwingConstants.CENTER);
        backPanel.add(photoLabel);

        add(backPanel, BorderLayout.CENTER); // Add back panel to frame

        // Add window listener to handle fullscreen mode
        addWindowListener(new WindowAdapter() {
            @Override
            public void windowOpened(WindowEvent e) {
                setUndecorated(true); // Remove window decorations
                // setAlwaysOnTop(true); // Keep the window on top of other applications
                backPanel.setSize(getWidth(), getHeight());
                getRootPane().setWindowDecorationStyle(JRootPane.NONE); // Remove window borders
                pack();
            }
        });

        photos = loadPhotos();
        if (photos.isEmpty())
            return;

        startPhotoLoop();
        startDateTimeUpdater();
    }

    private void startDateTimeUpdater() {
        timer = new Timer(1000, e -> updateDateTimeLabel());
        timer.start();
    }

    // region Animations
    public void setSegue(BufferedImage sourceImage, BufferedImage destinationImage) {
        switch (getRandInt(DEFAULT_MAX_ANIMATIONS)) {
            case 1:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        PixelDissolveEffect.class);
                break;
            case 2:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        AlphaDissolveEffect.class);
                break;
            case 3:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        CheckerboardEffect.class);
                break;
            case 4:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        BlindsEffect.class);
                break;
            case 5:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollLeftEffect.class);
                break;
            case 6:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollRightEffect.class);
                break;
            case 7:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollUpEffect.class);
                break;
            case 8:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollDownEffect.class);
                break;
            case 9:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeLeftEffect.class);
                break;
            case 10:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeRightEffect.class);
                break;
            case 11:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeUpEffect.class);
                break;
            case 12:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeDownEffect.class);
                break;
            case 13:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ZoomOutEffect.class);
                break;
            case 14:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ZoomInEffect.class);
                break;
            case 15:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        IrisOpenEffect.class);
                break;
            case 16:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        IrisCloseEffect.class);
                break;
            case 17:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        BarnDoorOpenEffect.class);
                break;
            case 18:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        BarnDoorCloseEffect.class);
                break;
            case 19:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ShrinkToBottomEffect.class);
                break;
            case 20:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ShrinkToTopEffect.class);
                break;
            case 21:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ShrinkToCenterEffect.class);
                break;
            case 22:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        StretchFromBottomEffect.class);
                break;
            case 23:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        StretchFromTopEffect.class);
                break;
            case 24:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        StretchFromCenterEffect.class);
                break;
            default:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollLeftEffect.class);
                break;
        }
    }

    public AnimatedSegue buildSegue(BufferedImage source, BufferedImage destination,
            Class<? extends AnimatedSegue> effectClass) {
        return SegueBuilder.of(effectClass)
                .withSource(source)
                .withDestination(destination)
                .withDuration((int) DEFAULT_ANIMATION_DURATION, TimeUnit.MILLISECONDS)
                .withMaxFramesPerSecond(DEFAULT_MAX_FPS)
                .withAnimationObserver(this)
                .withCompletionObserver(null)
                .build();
    }
    // endregion Animations

    private void setScreenSize() {
        Dimension screenSize = Toolkit.getDefaultToolkit().getScreenSize();

        // Get the screen width and height
        screenWidth = (int) screenSize.getWidth();
        screenHeight = (int) screenSize.getHeight();

        // Set the window Size
        setSize(screenSize.width, screenSize.height);
    }

    private void startPhotoLoop() {
        new Thread(() -> {
            BufferedImage resizedSourceImage = null;
            BufferedImage resizedDestinationImage = null;
            BufferedImage currentImage = null;
            BufferedImage nextImage = null;
			
            try {
            	currentImage = ImageIO.read(new File(photos.get(0)));
			} catch (IOException e) {
				e.printStackTrace();
				return;
			}
            
            while (m_isRunning) {
                int currentImageIdx = getRandInt(photos.size() - 1);
                int nextImageIdx = getRandInt(photos.size() - 1);

                while (currentImageIdx == nextImageIdx) {
                    // Make sure not to show the same image twice, also if there are not lot of
                    // images,
                    // skip this loop. this is a very rare occasion with large image libraries.
                    if (photos.size() < 10)
                        break;
                    nextImageIdx = getRandInt(photos.size() - 1);
                }

                try {
                	//currentImage = ImageIO.read(new File(photos.get(currentImageIdx)));
					nextImage = ImageIO.read(new File(photos.get(nextImageIdx % photos.size())));
               
                    resizedSourceImage = resizeImage(currentImage, screenWidth, screenHeight);
                    resizedDestinationImage = resizeImage(nextImage, screenWidth, screenHeight);
                	
                    if (resizedSourceImage == null || resizedSourceImage.getWidth() != screenWidth
                            || resizedSourceImage.getHeight() != screenHeight) {
                        resizedSourceImage = resizeImage(currentImage, screenWidth, screenHeight);
                    }

                    if (resizedDestinationImage == null || resizedDestinationImage.getWidth() != screenWidth
                            || resizedDestinationImage.getHeight() != screenHeight) {
                        resizedDestinationImage = resizeImage(nextImage, screenWidth, screenHeight);
                    }

                    setSegue(resizedSourceImage, resizedDestinationImage);
                    currentSegue.start();
                    currentImage= nextImage;
                    
                    Thread.sleep(DEFAULT_SLEEP_DURATION);
                } catch (IOException e) {
                    e.printStackTrace();
                    continue;
                } catch (InterruptedException e) {
                    m_isRunning = false;
                    break;
                }
            }
        }).start();
    }

    private List<String> loadPhotos() {
        List<String> paths = new ArrayList<>();
        try {
            String path = appSettings.ImagesPath;
            if (path == null) {
                path = "./resources";

                if (m_IsDebug)
                    path = "./src/main/java/org/alws/photoframe/resources";
            }

            Path directoryPath = Paths.get(path);
            if (!Files.exists(directoryPath)) {
                Files.createDirectories(directoryPath);
                throw new Exception(
                        "Created new Directory \"resources\". please add some photos and restart the app.");
            }

            // Use Stream API and Path API
            paths = Files.list(directoryPath)
                    .filter(file -> file.toFile().isFile() &&
                            (file.toString().toLowerCase().endsWith(".jpg") ||
                                    file.toString().toLowerCase().endsWith(".png") ||
                                    file.toString().toLowerCase().endsWith(".jpeg") ||
                                    file.toString().toLowerCase().endsWith(".heic") ||
                                    file.toString().toLowerCase().endsWith(".heif")))
                    .map(Path::toString)
                    .collect(Collectors.toList());
        } catch (Exception e) {
            e.printStackTrace();
        }
        return paths;
    }

    private BufferedImage resizeImage(BufferedImage image, int width, int height) {
        BufferedImage resizedImage = new BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = resizedImage.createGraphics();
        g2d.drawImage(image.getScaledInstance(width, height, Image.SCALE_SMOOTH), 0, 0, null);
        g2d.dispose();
        return resizedImage;
    }

    @Override
    public void onFrameRendered(AnimatedSegue segue, BufferedImage image) {
        photoLabel.setIcon(new ImageIcon(image));
    }

    private void updateDateTimeLabel() {
        String date = new SimpleDateFormat(appSettings.DateFormat).format(new Date());
        String time = new SimpleDateFormat(appSettings.TimeFormat).format(new Date());
        timeLabel.setText(time);
        dateLabel.setText(date);
    }

    public static int getRandInt(int max) {
        Random random = new Random();
        return random.nextInt(max) + 1;
    }

    public static String readFile(String filePath) throws IOException {

        StringBuilder content = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(filePath))) {
            String line;
            while ((line = reader.readLine()) != null) {
                content.append(line).append("\n");
            }
        } catch (Exception e) {
            return null;
        }
        return content.toString().trim();
    }
}
