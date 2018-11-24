import math
import torch
import torch.nn as nn
import torch.utils.model_zoo as model_zoo


class Bottleneck(nn.Module):
    expansion = 4

    def __init__(
        self,
        inplanes,
        planes,
        stride=1,
        dilation=1,
        downsample=None,
        BatchNorm=nn.BatchNorm2d,
    ):
        super(Bottleneck, self).__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = BatchNorm(planes)
        self.conv2 = nn.Conv2d(
            planes,
            planes,
            kernel_size=3,
            stride=stride,
            dilation=dilation,
            padding=dilation,
            bias=False,
        )
        self.bn2 = BatchNorm(planes)
        self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = BatchNorm(planes * 4)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride
        self.dilation = dilation

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out


class ResNet(nn.Module):
    def __init__(
        self,
        layers,
        output_stride,
        num_in_layers=3,
        block=Bottleneck,
        BatchNorm=nn.BatchNorm2d,
        pretrained=False,
    ):
        self.inplanes = 64
        super(ResNet, self).__init__()
        # output_stride = 64 is the basic case
        # of resnet50_md from Godard et al
        # if blocks is set to  [1, 1, 1], then
        # this is equivalent to calling _make_layer in the last block instead of __make_multigrid_unit
        if output_stride == 64:
            strides = [2, 2, 2, 2]
            dilations = [1, 1, 1, 1]
        # output_stride = 32 starts decreasing the size one block later
        elif output_stride == 32:
            strides = [1, 2, 2, 2]
            dilations = [1, 1, 1, 1]
        # output_stride = 16 is the standard for deeplabv3+
        elif output_stride == 16:
            strides = [1, 2, 2, 1]
            dilations = [1, 1, 1, 2]
        elif output_stride == 8:
            strides = [1, 2, 1, 1]
            dilations = [1, 1, 2, 4]
        else:
            raise NotImplementedError

        # Modules
        self.conv1 = nn.Conv2d(
            num_in_layers, 64, kernel_size=7, stride=2, padding=3, bias=False
        )
        self.bn1 = BatchNorm(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        self.layer1 = self._make_layer(
            block,
            64,
            layers[0],
            stride=strides[0],
            dilation=dilations[0],
            BatchNorm=BatchNorm,
        )
        self.layer2 = self._make_layer(
            block,
            128,
            layers[1],
            stride=strides[1],
            dilation=dilations[1],
            BatchNorm=BatchNorm,
        )
        self.layer3 = self._make_layer(
            block,
            256,
            layers[2],
            stride=strides[2],
            dilation=dilations[2],
            BatchNorm=BatchNorm,
        )
        self.layer4 = self._make_layer(
            block,
            512,
            layers[3],
            stride=strides[3],
            dilation=dilations[3],
            BatchNorm=BatchNorm,
        )
        self._init_weight()

        if pretrained:
            self._load_pretrained_model()

    def _make_layer(
        self,
        block: Bottleneck,
        planes: int,
        blocks: int,
        stride=1,
        dilation=1,
        BatchNorm=None,
    ) -> nn.Sequential:
        """
        Generate a layer block
        Args:
            block: Block type
            planes: Number of planes
            blocks: Number of blocks
            stride: Convolution stride for each convolution layer
            dilation: Atrous rate
        :return: Sequential model
        """
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(
                    self.inplanes,
                    planes * block.expansion,
                    kernel_size=1,
                    stride=stride,
                    bias=False,
                ),
                BatchNorm(planes * block.expansion),
            )

        layers = []
        layers.append(
            block(self.inplanes, planes, stride, dilation, downsample, BatchNorm)
        )
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes, BatchNorm=BatchNorm))

        return nn.Sequential(*layers)

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        x1 = self.conv1(input)
        x_pool1 = self.bn1(x1)
        x_pool1 = self.relu(x_pool1)
        x_pool1 = self.maxpool(x_pool1)

        x2 = self.layer1(x_pool1)
        x3 = self.layer2(x2)
        x4 = self.layer3(x3)
        x_out = self.layer4(x4)
        return x1, x_pool1, x2, x3, x4, x_out

    def _init_weight(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2.0 / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _load_pretrained_model(self):
        pretrain_dict = model_zoo.load_url(
            "https://download.pytorch.org/models/resnet101-5d3b4d8f.pth"
        )
        model_dict = {}
        state_dict = self.state_dict()
        for k, v in pretrain_dict.items():
            if k in state_dict:
                model_dict[k] = v
        state_dict.update(model_dict)
        self.load_state_dict(state_dict)


def ResNet101(output_stride, num_in_layers=3, pretrained=False):
    """Constructs a ResNet-101 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNet(
        [3, 4, 23, 3],
        output_stride,
        num_in_layers=num_in_layers,
        block=Bottleneck,
        pretrained=pretrained,
    )
    return model


def ResNet50(output_stride, num_in_layers=3, pretrained=False):
    """Constructs a ResNet-101 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNet(
        [3, 4, 6, 3],
        output_stride,
        num_in_layers=num_in_layers,
        block=Bottleneck,
        pretrained=pretrained,
    )
    return model


def Resnet18(output_stride, num_in_layers=3, pretrained=False):
    """Constructs a ResNet-101 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNet(
        [2, 2, 2, 2],
        output_stride,
        num_in_layers=num_in_layers,
        block=Bottleneck,
        pretrained=pretrained,
    )
    return model


if __name__ == "__main__":
    import torch

    x = torch.rand(1, 3, 512, 512)

    for out_stride in [16, 32, 64]:
        net = ResNet(block=Bottleneck, layers=[3, 4, 6, 3], output_stride=out_stride)

        y = net.forward(x)

        print("Output stride: {}".format(out_stride))
        for yi in y:
            print(yi.size())