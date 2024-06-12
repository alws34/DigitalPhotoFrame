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


import java.util.*;
import java.awt.image.*;
import javax.imageio.ImageIO;
import javax.swing.*;
import java.awt.geom.AffineTransform;

import javax.imageio.ImageIO;
import javax.swing.*;
import java.util.Random;

public class PhotoFrame extends JFrame implements SegueAnimationObserver {

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
    private ImageProcessor imageProcessor;
    private final boolean m_IsDebug = false;

    public PhotoFrame() {
        super("Photo Frame");
        setExtendedState(JFrame.MAXIMIZED_BOTH);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        if (!m_IsDebug)
            this.setUndecorated(true); // Remove window decorations

        String jsonString;

        if (m_IsDebug)
            System.out.println(System.getProperty("user.dir"));

        String filePath = "./src/main/java/settings.json";

        if (m_IsDebug)
            filePath = "./settings.json";

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
        backPanel.setBackground(Color.BLACK);
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


        // Assign the appropriate function to the image processor based on DefaultVerticalImageEffect
        switch (appSettings.DefaultVerticalImageEffect) {
            case 1:
                imageProcessor = this::processVerticalImage;
                break;
            case 2:
                imageProcessor = this::processVerticalImage2;
                break;
            case 3:
                imageProcessor = this::processVerticalImage3;
                break;
            default:
                throw new IllegalArgumentException("Invalid DefaultVerticalImageEffect: " + appSettings.DefaultVerticalImageEffect);
        }

        startPhotoLoop();
        startDateTimeUpdater();
    }

    private void startDateTimeUpdater() {
        timer = new javax.swing.Timer(1000, e -> updateDateTimeLabel());
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

    private void startPhotoLoop() {
        new Thread(() -> {
            BufferedImage resizedSourceImage = null;
            BufferedImage resizedDestinationImage = null;
            BufferedImage currentImage = null;
            BufferedImage nextImage = null;
			
            try {
            	currentImage = ImageIO.read(new File(photos.get( getRandInt(photos.size() - 1))));
			} catch (IOException e) {
				e.printStackTrace();
				return;
			}

            while (m_isRunning) {
                int currentImageIdx = getRandInt(photos.size() - 1);
                int nextImageIdx = getRandInt(photos.size() - 1);

                while (currentImageIdx == nextImageIdx) {
                    if (photos.size() < 10)
                        break;
                    nextImageIdx = getRandInt(photos.size() - 1);
                }

                try {
                    nextImage = ImageIO.read(new File(photos.get(nextImageIdx % photos.size())));

                    if (isImageVertical(currentImage)) {
                        currentImage = imageProcessor.process(currentImage);
                    } else {
                        currentImage = resizeImage(currentImage, screenWidth, screenHeight);
                    }

                    if (isImageVertical(nextImage)) {
                        nextImage = imageProcessor.process(nextImage);
                    } else {
                        nextImage = resizeImage(nextImage, screenWidth, screenHeight);
                    }

                    resizedSourceImage = resizeImage(currentImage, screenWidth, screenHeight);

                    setSegue(resizedSourceImage, nextImage);
                    currentSegue.start();
                    currentImage = nextImage;

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
    private boolean isImageVertical(BufferedImage image) {
        return image.getHeight() > image.getWidth();
    }

    @FunctionalInterface
    interface ImageProcessor {
        BufferedImage process(BufferedImage image);
    }

    /**
     * Processes a vertical image by applying a frosted glass effect, resizing it,
     * and combining it to create a visually appealing background for the original image.
     * <p>
     * The method performs the following steps:
     * <ul>
     *     <li>Stretches the image to fit half of the screen width while maintaining the full screen height.</li>
     *     <li>Applies an average filter (frosted glass effect) with a large kernel size to the resized image.</li>
     *     <li>Combines two blurred images side by side to fill the entire screen width.</li>
     *     <li>Overlays the original image centered on the combined blurred images.</li>
     * </ul>
     *
     * @param image The original vertical image to be processed.
     * @return A new {@link BufferedImage} containing the processed image with a frosted glass effect background.
     */
    private BufferedImage processVerticalImage(BufferedImage image) {
        int targetWidth = screenWidth;
        int targetHeight = screenHeight;

        // Stretch image to fit screen dimensions (no rotation)
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

        // Overlay original image centered on frosted image
        BufferedImage finalImage = overlayImage(frostedImage, image, (targetWidth - image.getWidth()) / 2, (targetHeight - image.getHeight()) / 2);

        return finalImage;
    }

    /**
     * Processes a vertical image by applying a frosted glass effect, resizing it,
     * and combining it to create a visually appealing background for the original image.
     * the difference between this and @processVerticalImage is that this method will display 2 blurred
     * images side by side and the original image on top.
     * <p>
     * The method performs the following steps:
     * <ul>
     *     <li>Stretches the image to fit half of the screen width while maintaining the full screen height.</li>
     *     <li>Applies an average filter (frosted glass effect) with a large kernel size to the resized image.</li>
     *     <li>Combines two blurred images side by side to fill the entire screen width.</li>
     *     <li>Overlays the original image centered on the combined blurred images.</li>
     * </ul>
     *
     * @param image The original vertical image to be processed.
     * @return A new {@link BufferedImage} containing the processed image with a frosted glass effect background.
     */
    private BufferedImage processVerticalImage2(BufferedImage image) {
        int targetWidth = screenWidth;
        int targetHeight = screenHeight;

        // Stretch image to fit half of the screen width while maintaining full screen height
        int halfWidth = targetWidth / 2;
        BufferedImage stretchedImage = new BufferedImage(halfWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = stretchedImage.createGraphics();
        g2d.drawImage(image, 0, 0, halfWidth, targetHeight, null);
        g2d.dispose();

        // Apply average filter (frosted glass effect) with a larger kernel
        int kernelSize = 50; // Larger kernel for a stronger frosted effect
        int kernelRadius = kernelSize / 2;

        BufferedImage frostedImage = new BufferedImage(halfWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        for (int y = 0; y < targetHeight; y++) {
            for (int x = 0; x < halfWidth; x++) {
                int red = 0, green = 0, blue = 0, count = 0;
                // Sample neighboring pixels (larger kernel size)
                for (int i = -kernelRadius; i <= kernelRadius; i++) {
                    for (int j = -kernelRadius; j <= kernelRadius; j++) {
                        int currentX = x + i;
                        int currentY = y + j;
                        if (currentX < 0 || currentX >= halfWidth || currentY < 0 || currentY >= targetHeight) {
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

        // Create a new image to combine two blurred images side by side
        BufferedImage combinedBlurredImage = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        g2d = combinedBlurredImage.createGraphics();
        g2d.drawImage(frostedImage, 0, 0, null);
        g2d.drawImage(frostedImage, halfWidth, 0, null);
        g2d.dispose();

        // Overlay original image centered on combined blurred images
        BufferedImage finalImage = overlayImage(combinedBlurredImage, image, (targetWidth - image.getWidth()) / 2, (targetHeight - image.getHeight()) / 2);

        return finalImage;
    }

    private BufferedImage processVerticalImage3(BufferedImage image) {
        int targetWidth = screenWidth;
        int targetHeight = screenHeight;

        // Create a blank image with the dimensions of the screen
        BufferedImage finalImage = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = finalImage.createGraphics();

        // Calculate the position to center the image
        int x = (targetWidth - image.getWidth()) / 2;
        int y = (targetHeight - image.getHeight()) / 2;

        // Draw the original image centered on the blank image
        g2d.drawImage(image, x, y, null);
        g2d.dispose();

        return finalImage;
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

    private List<String> loadPhotos() {
        List<String> paths = new ArrayList<>();
        try {
            String path = appSettings.ImagesPath;
            if (path == null) {
                path = "./src/main/resources";

                if (m_IsDebug)
                    path = "../resources";
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

    private BufferedImage resizeImage(BufferedImage image, int targetWidth, int targetHeight) {
        BufferedImage resizedImage = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = resizedImage.createGraphics();
        g2d.drawImage(image, 0, 0, targetWidth, targetHeight, null);
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

    public static void main(String[] args) {
        PhotoFrame frame = new PhotoFrame();
        frame.setVisible(true);
    }
}
