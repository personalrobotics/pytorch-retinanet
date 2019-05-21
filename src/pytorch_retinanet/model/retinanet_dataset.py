from __future__ import print_function
from __future__ import division

import sys
import os
import random

import torch
import torch.utils.data as data

from PIL import Image, ImageEnhance

from pytorch_retinanet.utils.encoder import DataEncoder
from pytorch_retinanet.utils.transform import resize, resize_box, random_flip, random_crop, center_crop
from pytorch_retinanet.utils.utils import load_label_map
from pytorch_retinanet.utils.pt_utils import one_hot_embedding
from pytorch_retinanet.config import config


class ListDataset(data.Dataset):
    def __init__(self,
                 img_dir=config.img_dir,
                 list_filename=config.train_list_filename,
                 label_map_filename=config.label_map_filename,
                 train=True,
                 transform=None,
                 input_size=config.img_res):

        self.img_dir = img_dir
        self.train = train
        self.transform = transform
        self.input_size = input_size

        self.label_map = load_label_map(label_map_filename)

        self.img_filenames = list()
        self.boxes = list()
        self.labels = list()

        self.encoder = DataEncoder()

        with open(list_filename) as f:
            lines = f.readlines()
            self.num_samples = len(lines)
            f.close()

        isize = 5
        print("Validating Dataset...")
        for i, line in enumerate(lines):
            if i % 100 == 0:
                print("Processing %d / %d" % (i, self.num_samples))
            splited = line.strip().split()

            this_img_filename = splited[0]

            num_boxes = (len(splited) - 1) // isize
            box = list()
            label = list()
            for bidx in range(num_boxes):
                xmin = float(splited[1 + isize * bidx])
                ymin = float(splited[2 + isize * bidx])
                xmax = float(splited[3 + isize * bidx])
                ymax = float(splited[4 + isize * bidx])
                cls = int(splited[5 + isize * bidx])
                box.append([xmin, ymin, xmax, ymax])
                label.append(cls)

            if not self._validate_init(this_img_filename, box, label):
                self.num_samples -= 1
                continue

            self.img_filenames.append(this_img_filename)
            self.boxes.append(torch.Tensor(box))
            self.labels.append(torch.LongTensor(label))

        print("Finished! %d Samples Validated" % self.num_samples)

    def _validate_init(self, img_filename, box, label):
        h = w = self.input_size
        img = Image.open(os.path.join(self.img_dir, img_filename))
        boxes = resize_box(img, torch.Tensor(box), (w, h))
        labels = torch.LongTensor(label)
        this_cls = self.encoder.encode_validate(
                boxes, labels, input_size=(w, h))
        return (this_cls.max(0)[0] > 0)

    def _validate_getitem(self, img, box, labels):
        h = w = self.input_size
        boxes = resize_box(img, box, (w, h))
        this_cls = self.encoder.encode_validate(
                boxes, labels, input_size=(w, h))
        return (this_cls.max(0)[0] > 0)

    def __getitem__(self, idx):
        img_filename = self.img_filenames[idx]
        img = Image.open(os.path.join(self.img_dir, img_filename))
        if img.mode != 'RGB':
            img = img.convert('RGB')

        boxes = self.boxes[idx].clone()
        labels = self.labels[idx]
        size = self.input_size

        # Data augmentation
        if self.train:
            img_new, boxes_new = random_flip(img, boxes)
            img_new, boxes_new = random_crop(img_new, boxes_new)
            img_new, boxes_new = resize(img_new, boxes_new, (size, size))
            if not self._validate_getitem(img_new, boxes_new, labels):
                img, boxes = resize(img, boxes, (size, size))
            else:
                img = img_new
                boxes = boxes_new
                if random.random() > 0.5:
                    img = ImageEnhance.Color(img).enhance(random.uniform(0, 1))
                    img = ImageEnhance.Brightness(img).enhance(random.uniform(0.5, 2))
                    img = ImageEnhance.Contrast(img).enhance(random.uniform(0.5, 1.5))
                    img = ImageEnhance.Sharpness(img).enhance(random.uniform(0.5, 1.5))
        else:
            img, boxes = resize(img, boxes, (size, size))

        img = self.transform(img)
        return img, boxes, labels

    def collate_fn(self, batch):
        imgs = [x[0] for x in batch]
        boxes = [x[1] for x in batch]
        labels = [x[2] for x in batch]

        h = w = self.input_size
        num_imgs = len(imgs)
        inputs = torch.zeros(num_imgs, 3, h, w)

        loc_targets = list()
        cls_targets = list()
        for i in range(num_imgs):
            inputs[i] = imgs[i]
            this_loc, this_cls = self.encoder.encode(
                boxes[i], labels[i], input_size=(w, h))
            loc_targets.append(this_loc)
            cls_targets.append(this_cls)

        return inputs, torch.stack(loc_targets), torch.stack(cls_targets)

    def __len__(self):
        return self.num_samples


def test():
    print('[listdataset] test')
    ds = ListDataset(
        list_filename=config.test_list_filename,
        train=False)
    import IPython; IPython.embed()


if __name__ == '__main__':
    test()
