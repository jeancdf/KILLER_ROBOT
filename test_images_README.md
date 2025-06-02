# Test Images Directory

This directory is intended for storing test images to use with the `test_on_image.py` script.

## How to Use

1. Create a directory named `test_images` in the project root:
   ```
   mkdir test_images
   ```

2. Add any test images to this directory.

3. Run the test script on an image:
   ```
   python test_on_image.py --image test_images/your_image.jpg
   ```

## Recommended Test Images

For testing human detection, consider using images that contain:
- Single person in clear view
- Multiple people at different distances
- People in different poses
- People partially occluded
- Scenes with potential false positives (mannequins, statues, etc.)

## Sample Images

You can download sample images from various sources:
- [COCO Dataset](https://cocodataset.org/)
- [Open Images Dataset](https://storage.googleapis.com/openimages/web/index.html)
- [Unsplash](https://unsplash.com/) (search for "people" or "person")

## Note

Test images are excluded from version control in .gitignore to avoid storing large binary files in the repository. 