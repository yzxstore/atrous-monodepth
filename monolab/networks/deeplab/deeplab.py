import torch
import torch.nn as nn
from torch import Tensor
from typing import List

from monolab.networks.backbones.resnet import ResNet50, Bottleneck
from monolab.networks.backbones.xception import Xception
from monolab.networks.deeplab.deeplab_decoder import Decoder
from monolab.networks.deeplab.aspp import ASPP

from monolab.networks.utils import DisparityOut


class DeepLab(nn.Module):
    def __init__(
        self, num_in_layers=3, backbone="resnet", output_stride=16, freeze_bn=False
    ):
        super(DeepLab, self).__init__()

        self.dcnn_type = backbone

        # Define backbone DCNN in encoder
        if backbone == "resnet":
            self.backbone = ResNet50(
                output_stride=output_stride, num_in_layers=num_in_layers
            )
        elif backbone == "xception":
            self.backbone = Xception(
                inplanes=num_in_layers, output_stride=output_stride, pretrained=False
            )
        else:
            raise NotImplementedError(f"Backbone {backbone} not found.")

        # ASPP module
        self.aspp = ASPP(backbone, output_stride, BatchNorm=nn.BatchNorm2d)

        # Decoder module
        if backbone == "resnet":
            # Output channel sizes of x4 x3 x2 x1 of resnet
            x_low_inplanes_list = [256 * 4, 128 * 4, 64 * 4, 64]
        else:
            raise NotImplementedError(f"Backbone {backbone} not found.")

        num_channels_out_list = [128, 64, 32, 16]
        self.decoder = Decoder(
            backbone=backbone,
            BatchNorm=nn.BatchNorm2d,
            x_low_inplanes_list=x_low_inplanes_list,
            num_outplanes_list=num_channels_out_list,
        )

        self.disp1 = DisparityOut(num_channels_out_list[0])
        self.disp2 = DisparityOut(num_channels_out_list[1])
        self.disp3 = DisparityOut(num_channels_out_list[2])
        self.disp4 = DisparityOut(num_channels_out_list[3])

        if freeze_bn:
            self.freeze_bn()

    def forward(self, x):
        if self.dcnn_type == "resnet":
            x1, x1_pool, x2, x3, x4, x_dcnn_out = self.backbone(x)
        elif self.dcnn_type == "xception":
            x_dcnn_out, x2 = self.backbone(input)
            raise NotImplementedError(
                "Multiple disparities for xception backend not " "yet implemented"
            )
        else:
            raise NotImplementedError(
                "Unknown DCNN backend type for the Deeplab backbone."
            )

        # Apply ASPP module
        x = self.aspp(x_dcnn_out)

        # List of decoder results of size num_disparity_maps
        x_decoder_results: List[Tensor] = self.decoder(x, [x4, x3, x2, x1])

        # Compute disparity maps
        disp1 = self.disp1(x_decoder_results[0])
        disp2 = self.disp2(x_decoder_results[1])
        disp3 = self.disp3(x_decoder_results[2])
        disp4 = self.disp4(x_decoder_results[3])
        return [disp4, disp3, disp2, disp1]

    def freeze_bn(self):
        for m in self.modules():
            if isinstance(m, nn.BatchNorm2d):
                m.eval()


if __name__ == "__main__":
    x = torch.rand(1, 3, 256, 512)

    net = DeepLab(num_in_layers=3, output_stride=16, backbone="resnet")
    print(net)

    net.eval()

    y = net.forward(x)

    for yi in y:
        print(yi.size())
