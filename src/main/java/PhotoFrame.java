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
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.text.SimpleDateFormat;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import javax.imageio.ImageIO;
import javax.swing.*;
import javax.swing.Timer;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

public class PhotoFrame extends JFrame implements SegueAnimationObserver {

    private final boolean m_IsDebug = false;

    private static final int BLUR_RADIUS = 100;
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
    AppSettings appSettings = new AppSettings();
    private boolean m_isRunning = true;
    private javax.swing.Timer timer = null;
    private javax.swing.Timer photosTimer = null;
    private static final Set<String> SUPPORTED_EXTENSIONS = Set.of(".jpg", ".png", ".jpeg", ".heic", ".heif");

    BufferedImage currentImage = null;
    BufferedImage nextImage = null;

    public PhotoFrame() {
        super("Photo Frame");
        setExtendedState(JFrame.MAXIMIZED_BOTH);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        if (!m_IsDebug)
            this.setUndecorated(true); // Remove window decorations

        // Transparent 16 x 16 pixel cursor image.
        BufferedImage cursorImg = new BufferedImage(16, 16, BufferedImage.TYPE_INT_ARGB);

        // Create a new blank cursor.
        Cursor blankCursor = Toolkit.getDefaultToolkit().createCustomCursor(
                cursorImg, new Point(0, 0), "blank cursor");

        // Set the blank cursor to the JFrame.
        this.getContentPane().setCursor(blankCursor);


        addWindowListener(new WindowAdapter() {
            @Override
            public void windowOpened(WindowEvent e) {
                frameShow();
                setUndecorated(true); // Remove window decorations
                // setAlwaysOnTop(true); // Keep the window on top of other applications
                backPanel.setSize(getWidth(), getHeight());
                getRootPane().setWindowDecorationStyle(JRootPane.NONE); // Remove window borders
                pack();
            }
        });


        String settingsStr;

        if (m_IsDebug)
            System.out.println(System.getProperty("user.dir"));

        String filePath = m_IsDebug ? "./src/main/java/settings.json" : "./settings.json";

        try {
            settingsStr = readFile(filePath);

            if (settingsStr == null) {
                logException(new Exception("Cant read json string from file"));
                m_isRunning = false;
                return;
            }
            appSettings = AppSettings.deserialize(settingsStr);
        } catch (IOException e) {
            logException(e);
            m_isRunning = false;
            return;
        }

        DEFAULT_ANIMATION_DURATION = appSettings.DefaultAnimationDuration;
        DEFAULT_SLEEP_DURATION = appSettings.DelayBetweenImages;
        DEFAULT_MAX_FPS = appSettings.DefaultMaxFPS;
        try {
            photos = loadPhotos();
            if (photos.isEmpty()) {
                logException(new Exception("Photos list is empty"));
                m_isRunning = false;
                return;
            }
        }catch (IOException ioe)
        {
            logException(ioe);
        }
        startPhotoLoop();
        startTimers();
    }

    private void frameShow()
    {
        backPanel = new JPanel();
        SpringLayout springLayout = new SpringLayout();
        backPanel.setLayout(springLayout);
        backPanel.setBackground(Color.BLACK);

        Color foregroundColor = Color.decode(appSettings.colorHex);
        String fontName = appSettings.FontName;

        setScreenSize();

        // Create and set up the time label
        timeLabel = new JLabel();
        timeLabel.setFont(new Font(fontName, Font.BOLD, 100));
        timeLabel.setForeground(foregroundColor);

        // Position the time label in the bottom-left corner
        springLayout.putConstraint(SpringLayout.WEST, timeLabel, 10, SpringLayout.WEST, backPanel);
        springLayout.putConstraint(SpringLayout.SOUTH, timeLabel, -60, SpringLayout.SOUTH, backPanel);
        backPanel.add(timeLabel);

        // Create and set up the date label
        dateLabel = new JLabel();
        dateLabel.setFont(new Font(fontName, Font.BOLD, 50));
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
    }

    private void startTimers() {
        timer = new javax.swing.Timer(1000, e -> updateDateTimeLabel());
        timer.start();
        photosTimer = new javax.swing.Timer(DEFAULT_SLEEP_DURATION, e -> startPhotoLoop());
        photosTimer.start();
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
            default:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        StretchFromCenterEffect.class);
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


    private void ChangePhoto(){
        int size = photos.size() - 1;

        int currentImageIdx = getRandInt(size);
        int nextImageIdx = getRandInt(size);

        while (currentImageIdx == nextImageIdx) {
            if(size <= 10)
                break;
            nextImageIdx =getRandInt(size);
        }

        try {
            currentImage = ImageIO.read(new File(photos.get(currentImageIdx)));
            nextImage = ImageIO.read(new File(photos.get(nextImageIdx)));

            currentImage = resizeImage(currentImage);
            nextImage = resizeImage(nextImage);

            setSegue(currentImage, nextImage);
            currentSegue.start();
            Thread.sleep(7000);
            currentImage = nextImage;
        } catch (IOException e) {
            logException(e);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
    }
    boolean isFirst = true;
    private void startPhotoLoop() {
        new Thread(() -> {
            int size = photos.size() - 1;
            int currentImageIdx = getRandInt(size);
            int nextImageIdx = getRandInt(size);




            while (currentImageIdx == nextImageIdx) {
                if(size <= 10)
                    break;
                nextImageIdx =getRandInt(size);
            }

            try {
                if(isFirst) {
                    currentImage = ImageIO.read(new File(photos.get(currentImageIdx)));
                    currentImage = resizeImage(currentImage);
                    isFirst = false;
                }
                nextImage = ImageIO.read(new File(photos.get(nextImageIdx)));

                nextImage = resizeImage(nextImage);

                setSegue(currentImage, nextImage);
                currentSegue.start();

                if (currentImage != null) {
                    currentImage.flush();
                }
                Thread.sleep(DEFAULT_SLEEP_DURATION / 3);

                currentImage = nextImage;

            } catch (IOException e) {
                logException(e);
            } catch (InterruptedException e) {
                throw new RuntimeException(e);
            }
        }).start();
    }

    private boolean isImageVertical(BufferedImage image) {
        return image.getHeight() > image.getWidth();
    }

    public BufferedImage resizeImage(BufferedImage image) {
        int imageWidth = image.getWidth();
        int imageHeight = image.getHeight();

        int targetWidth;
        int targetHeight;

        if (isImageVertical(image)) {
            // Resize vertical image to fit inside screen while keeping it vertical
            targetHeight = screenHeight;
            targetWidth = (int) ((double) targetHeight / imageHeight * imageWidth);
            if (targetWidth > screenWidth) {
                targetWidth = screenWidth;
                targetHeight = (int) ((double) targetWidth / imageWidth * imageHeight);
            }
        } else {
            // Resize non-vertical image to fit the entire screen while maintaining aspect ratio
            double screenAspectRatio = (double) screenWidth / screenHeight;
            double imageAspectRatio = (double) imageWidth / imageHeight;

            if (imageAspectRatio > screenAspectRatio) {
                // Image is wider than the screen aspect ratio
                targetWidth = screenWidth;
                targetHeight = (int) (screenWidth / imageAspectRatio);
            } else {
                // Image is taller than the screen aspect ratio
                targetHeight = screenHeight;
                targetWidth = (int) (screenHeight * imageAspectRatio);
            }
        }

        BufferedImage resizedImage = new BufferedImage(screenWidth, screenHeight, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = resizedImage.createGraphics();
        int x = (screenWidth - targetWidth) / 2;
        int y = (screenHeight - targetHeight) / 2;
        g2d.drawImage(image, x, y, targetWidth, targetHeight, null);
        g2d.dispose();

        image.flush();
        return resizedImage;
    }

    private BufferedImage processVerticalImage(BufferedImage image) {
        int targetWidth = screenWidth;
        int targetHeight = screenHeight;

        // Stretch image to fit screen dimensions (optional: adjust positioning)
        BufferedImage stretchedImage = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = stretchedImage.createGraphics();
        g2d.drawImage(image, 0, 0, targetWidth, targetHeight, null);
        g2d.dispose();

        // Apply average filter (frosted glass effect) with a larger kernel
        int kernelSize = 50; // Larger kernel for a stronger frosted effect
        int kernelRadius = kernelSize / 2;

        BufferedImage frostedImage = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        for (int y = 0; y < targetHeight; y++) {
            for (int x = 0; x < targetWidth; x++) {
                int red = 0, green = 0, blue = 0, count = 0;
                // Sample neighboring pixels (larger kernel size)
                for (int i = -kernelRadius; i <= kernelRadius; i++) {
                    for (int j = -kernelRadius; j <= kernelRadius; j++) {
                        int currentX = x + i;
                        int currentY = y + j;
                        if (currentX < 0 || currentX >= targetWidth || currentY < 0 || currentY >= targetHeight) {
                            continue; // Handle pixels outside the image bounds
                        }
                        int color = stretchedImage.getRGB(currentX, currentY);
                        red += (color >> 16) & 0xff;
                        green += (color >> 8) & 0xff;
                        blue += color & 0xff;
                        count++;
                    }
                }
                // Average the color values
                int avgRed = red / count;
                int avgGreen = green / count;
                int avgBlue = blue / count;
                frostedImage.setRGB(x, y, (0xff << 24) | (avgRed << 16) | (avgGreen << 8) | avgBlue);
            }
        }

        // Overlay original image centered on frosted image (optional: adjust positioning)
        BufferedImage finalImage = overlayImage(frostedImage, image, (targetWidth - image.getWidth()) / 2, (targetHeight - image.getHeight()) / 2);

        return finalImage;
    }

    private static void logException(Exception e) {
        LocalTime currentTime = LocalTime.now();
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("HH:mm:ss");
        String formattedTime = currentTime.format(formatter);

        try (FileWriter fw = new FileWriter("exceptions.log", true)) {
            fw.write( formattedTime + " **ERROR** ::" + e.toString() + "\n");

        } catch (IOException ioException) {
            ioException.printStackTrace();
        }
    }

    public static BufferedImage overlayImage(BufferedImage background, BufferedImage foreground, int x, int y) {
        int targetWidth = Math.max(background.getWidth(), foreground.getWidth() + x);
        int targetHeight = Math.max(background.getHeight(), foreground.getHeight() + y);
        BufferedImage finalImage = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = finalImage.createGraphics();
        g2d.drawImage(background, 0, 0, null);
        g2d.drawImage(foreground, x, y, null);
        g2d.dispose();
        return finalImage;
    }

    public List<String> loadPhotos() throws IOException {
        List<String> paths = new ArrayList<>();
        try {
            String path = Optional.ofNullable(appSettings.ImagesPath)
                    .orElse(m_IsDebug ? "./src/main/resources" : "./resources");

            Path directoryPath = Paths.get(path);

            if (!Files.exists(directoryPath)) {
                Files.createDirectories(directoryPath);
                Exception e = new Exception("Created new directory \"resources\". Please add photos and restart the app.");
                logException(e);
                return null;
            }

            paths = Files.list(directoryPath)
                    .filter(this::isSupportedImageFile)
                    .map(Path::toString)
                    .collect(Collectors.toList());
        } catch (Exception e) {
            logException(e);
            return null;
        }
        return paths;
    }

    private boolean isSupportedImageFile(Path file) {
        String fileName = file.getFileName().toString().toLowerCase();
        return Files.isRegularFile(file) && SUPPORTED_EXTENSIONS.stream().anyMatch(fileName::endsWith);
    }

    @Override
    public void onFrameRendered(AnimatedSegue segue, BufferedImage image) {
        try{
            photoLabel.setIcon(new ImageIcon(image));
        }
        catch (Exception e){
            logException(e);
        }
    }

    private void updateDateTimeLabel() {
        //setScreenSize();

        // Create and set up the time label
        //timeLabel = new JLabel();
        timeLabel.setFont(new Font(appSettings.FontName, Font.BOLD, 100));
        timeLabel.setForeground(Color.decode(appSettings.colorHex));

        dateLabel.setFont(new Font(appSettings.FontName, Font.BOLD, 50));
        dateLabel.setForeground(Color.decode(appSettings.colorHex));

        String date = new SimpleDateFormat(appSettings.DateFormat).format(new Date());
        String time = new SimpleDateFormat(appSettings.TimeFormat).format(new Date());

        timeLabel.setText(time);
        dateLabel.setText(date);
    }

    public static int getRandInt(int max) {
        Random rand = new Random();
        return rand.nextInt(max);
    }

    public static String readFile(String filePath) throws IOException {

        try{
            if (filePath == null) {
                Exception e = new IllegalArgumentException("File path cannot be null");
                logException(e);
                throw e;
            }

            return Files.readString(Paths.get(filePath), StandardCharsets.UTF_8).trim();
        } catch (Exception e) {
            logException(e);
            return null;
        }
    }

    public static void main(String[] args) {
        try{
            PhotoFrame frame = new PhotoFrame();

            frame.setVisible(true);
        }
        catch  (Exception e)
        {
            logException(e);
        }
    }
}
