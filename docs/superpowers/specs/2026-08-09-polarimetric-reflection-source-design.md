# Golden 双偏振连续有源反射源设计规格

## 1. 目标、权威和替代关系

本规格将 `D:\AWAY\RFSOC\model` 的 Golden 主目标冻结为双偏振连续有源反射源：

```text
8 路 ADC 连续复数输入
  -> H/V 入射波形重构
  -> 因果延迟、RCS、2x2 极化散射、多普勒和多目标叠加
  -> H/V 期望反射波
  -> TX 复标定预补偿
  -> 8 路 DAC 数学输出
```

原有 FIR、脉冲检测、PDW 和命中 IQ 记录保留为监测旁路。检测结果不得控制、阻塞或改变连续反射主链的样点位置。

本规格取代 `2026-08-03-golden-system-reference-design.md` 中以事件触发 LFM 发射为主的 `GoldenPulseSystem` 方向。旧文件作为历史设计记录保留，不再作为待实现目标。

本规格只覆盖 Golden 数学层。Cycle、生成 Verilog、RFDC Block Design、时钟/复位/CDC、时序收敛和板级验证必须分别设计和验收，不由 Golden 测试代替。

## 2. 选定方案

采用“新反射主链，复用旧检测旁路”方案：

```text
                    +-> 500 MSPS 连续反射主链 -> 8 路 DAC 数学输出
8 路 ADC @ 500 MSPS
                    +-> 2:1 FIR 抽取 -> 250 MSPS 检测/PDW/命中 IQ
```

不在现有 `GoldenPulseSystem` 上叠加 DRFM 行为，因为事件触发发射与连续相参转发具有不同的时间语义。不建立第二套模型包，避免复制采样域、舍入和配置权威。

## 3. 实施范围

### 3.1 本阶段包含

- 8 路 ADC 帧、H/V 波形、目标、标定和 8 路 DAC 帧公共契约；
- 静态硬件配置、运行场景和标定结果三类配置；
- 8 路 ADC 幅相/时延校准和 H/V 三量程重构；
- 固定量程和带滞回/保持的自动量程；
- 因果整数延迟和 63 抽头窗化 sinc 分数延迟 Golden 参考；
- 表观距离、固定内部延迟和可编程延迟换算；
- RCS 标定锚点到复数字电压增益的换算；
- 2x2 极化散射、多普勒和有限数量多目标复数叠加；
- TX 复标定预补偿和实际 8 路 DAC 逻辑路由；
- 原检测链作为只读监测旁路接入系统顶层；
- 确定性、因果性、物理量、通道映射和旧功能回归测试。

### 3.2 本阶段不包含

- Cycle 模型、RTL 生成或 Block Design 修改；
- AXI、FIFO、RAM、valid/ready、背压或缓存溢出语义；
- 闭环自适应主动对消；
- 多量程 `FUSED` 融合算法；
- 未经实测标定的绝对 RCS 精度承诺；
- 对 J4 扩展通道已经装配或通过板级测试的假定；
- RFDC DAC 实数/复数端口的最终硬件字级契约。

## 4. 采样域与数值边界

### 4.1 主链

反射主链使用：

```text
sample_domain  = RFDC_COMPLEX_INPUT
sample_rate_hz = rfdc_complex_sample_rate_hz
默认值         = 500_000_000 complex samples/s
```

主链不使用 PL 2:1 抽取后的检测数据。所有目标延迟均以该域的样点表示。

### 4.2 监测旁路

检测旁路继续使用：

```text
sample_domain  = DETECTOR
sample_rate_hz = detector_sample_rate_hz
默认值         = 250_000_000 samples/s
```

现有 `PulseRecord`、ADC 码、`I^2+Q^2` 功率单位、削顶传播、连续主峰 FWHM 和 ties-away-from-zero 舍入契约保持不变。

### 4.3 DAC 数学边界

Golden 内部反射和预补偿统一使用复基带包络。`EightChannelDacFrame` 在本阶段保存 8 路复基带数学包络及表示元数据，不宣称它已经等同于 RFDC DAC AXI 数据字。

进入 Cycle 设计前，必须结合 RFDC 配置冻结以下二选一硬件边界：

- 复基带 I/Q 输入，经 RFDC DUC/NCO 输出实 RF；
- 实数基带/中频输入及其相位表达方式。

Golden 测试验证包络数学和路由，不验证 RFDC 插值镜像或 NCO 配置。

## 5. 公共类型

### 5.1 正交通道属性

新增：

```python
class Polarization(str, Enum):
    H = "H"
    V = "V"

class GainRange(str, Enum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"
    REFERENCE = "reference"

class ChannelRole(str, Enum):
    ECHO = "echo"
    CALIBRATION = "calibration"
    CANCELLATION = "cancellation"
```

现有 `RangeId` 只用于旧 4 通道 PDW 兼容逻辑。新反射链禁止用一个枚举同时表达极化、增益档位和通道用途。

默认名义档位定义为 `HIGH=+20 dB`、`MID=0 dB`、`LOW=-20 dB`。实际复增益不由枚举推导，而由通道映射和 `CalibrationProfile` 提供。

### 5.2 H/V 波形

```python
@dataclass(frozen=True)
class PolarimetricWaveform:
    samples: np.ndarray       # complex128, shape=(2, N)
    sample_domain: SampleDomain
    sample_rate_hz: int
    start_sample: int = 0
```

固定下标：

```text
samples[0, :] = H
samples[1, :] = V
```

构造时拒绝非复数二维数组、首维不是 2、非正采样率或负 `start_sample`。

### 5.3 8 路 ADC/DAC 帧

```python
@dataclass(frozen=True)
class EightChannelAdcFrame:
    samples: np.ndarray       # complex128, shape=(8, N)
    clipped: np.ndarray       # bool, shape=(8, N)
    sample_domain: SampleDomain
    sample_rate_hz: int
    start_sample: int = 0

@dataclass(frozen=True)
class EightChannelDacFrame:
    samples: np.ndarray       # complex128, shape=(8, N)
    sample_domain: SampleDomain
    sample_rate_hz: int
    representation: str      # "complex_baseband_reference"
    start_sample: int = 0
```

ADC 主链只接受 `RFDC_COMPLEX_INPUT`。DAC 帧的采样率必须与预补偿后 H/V 波形相同。

## 6. 配置分层

### 6.1 `ModelConfig`：静态设计能力

在现有速率、数值格式和检测配置基础上增加：

```text
adc_channels = 8
dac_channels = 8
polarizations = 2
reflection_sample_rate_hz = 500_000_000
maximum_targets = 8
maximum_delay_samples = 1_048_576
fractional_delay_taps = 63
processing_representation = "complex_baseband"
dac_output_mode = "complex_baseband_reference"
adc_channel_map
dac_channel_map
```

必须满足：

```text
reflection_sample_rate_hz == rfdc_complex_sample_rate_hz
adc_channels == 8
dac_channels == 8
polarizations == 2
fractional_delay_taps 为正奇数
```

根目录 `config/default.json` 与安装包内 `rfsoc_pulse_model/config/default.json` 继续保持逐字节一致。

### 6.2 `ReflectionScenario`：一次运行的输入

包含：

- 设备物理距离；
- 载频；
- 目标列表；
- 模拟起始样点和持续长度；
- 当前温度。

### 6.3 `CalibrationProfile`：实测结果

包含：

- 固定内部总延迟；
- 8 路 ADC 复增益和相对分数时延；
- 8 路 DAC 复增益和相对分数时延；
- RX/TX 2x2 极化复传递矩阵；
- RCS 标定锚点；
- 标定频率、温度、版本和有效性信息。

固定内部延迟必须定义为从 ADC 数学输入边界到 DAC 数学输出边界的已标定总延迟，并明确是否已经包含未来硬件分数延迟器的固有群时延。Golden 编译使用该已标定总值，不重复添加群时延。

## 7. 物理通道映射

### 7.1 ADC 默认映射

在实测表更新前，按评审方案冻结默认逻辑映射：

| ADC | 极化 | 档位 | 用途 |
| --- | --- | --- | --- |
| ADC0 | H | HIGH | 入射重构 |
| ADC1 | H | MID | 入射重构 |
| ADC2 | H | LOW | 入射重构 |
| ADC3 | H | REFERENCE | 标定参考 |
| ADC4 | V | HIGH | 入射重构 |
| ADC5 | V | MID | 入射重构 |
| ADC6 | V | LOW | 入射重构 |
| ADC7 | V | REFERENCE | 标定参考 |

算法只读取配置映射，禁止硬编码上述索引。参考通道不参与普通三量程选择。

### 7.2 已确认 DAC 映射

| DAC | 极化 | 档位 | 用途 |
| --- | --- | --- | --- |
| DAC0 | V | HIGH | 回波 |
| DAC1 | H | HIGH | 回波 |
| DAC2 | V | MID | 回波 |
| DAC3 | H | MID | 回波 |
| DAC4 | V | LOW | 回波 |
| DAC5 | H | LOW | 回波 |
| DAC6 | V | REFERENCE | 校准或主动对消 |
| DAC7 | H | REFERENCE | 校准或主动对消 |

DAC6/7 的运行模式必须显式配置为 `CALIBRATION` 或 `CANCELLATION`。第一阶段允许校准波形或外部提供的抵消包络，不实现闭环自适应求解器。

## 8. Golden 模块边界与数据流

### 8.1 `GoldenEightChannelAdcFrontend`

输入 `EightChannelAdcFrame`，执行：

1. 每路复增益和相对时延校正；
2. 按配置识别 H/V 的高、中、低和参考通道；
3. 独立完成 H、V 量程选择；
4. 传播逐样点 clipping 和通道有效性；
5. 输出校准后的 8 路数组和 `PolarimetricWaveform`。

量程模式：

- `FIXED`：整次运行固定每个极化的档位；
- `AUTO_HOLD`：只在削顶或余量阈值越界时切换，使用滞回和最小保持样点数；
- `FUSED`：保留枚举但本阶段构造时拒绝启用。

默认反射和标定使用 `FIXED`。自动量程状态按极化独立，不能逐样点来回跳变。

### 8.2 `TargetCompiler`

用户目标：

```python
@dataclass(frozen=True)
class TargetRequest:
    apparent_range_m: float
    radial_velocity_mps: float
    target_rcs_m2: float
    normalized_scattering_matrix: np.ndarray  # complex128, shape=(2, 2)
    rcs_reference_channel: str = "HH"
    initial_phase_rad: float = 0.0
```

第一阶段只实现恒定径向速度。加速度目标留给后续目标运动规格，避免接口声明了反射内核无法表达的行为。

矩阵下标固定为：

```text
S[0,0] = H <- H (HH)
S[0,1] = H <- V (HV)
S[1,0] = V <- H (VH)
S[1,1] = V <- V (VV)
```

编译结果：

```python
@dataclass(frozen=True)
class CompiledScatterer:
    integer_delay_samples: int
    fractional_delay: float       # 0 <= value < 1
    doppler_hz: float
    complex_scattering_matrix: np.ndarray
```

目标编译负责距离、速度、RCS和标定换算。反射内核只接受 `CompiledScatterer`，不理解米、平方米或 UAV 位置。

速度符号约定为：`radial_velocity_mps > 0` 表示目标远离雷达，单基地多普勒为：

```text
doppler_hz = -2 * radial_velocity_mps * carrier_frequency_hz / c
```

### 8.3 因果延迟

总关系：

```text
tau_echo = 2 * physical_range / c + fixed_internal_delay + programmable_delay
```

因此：

```text
programmable_delay
  = 2 * (apparent_range - physical_range) / c
    - fixed_internal_delay
```

负可编程延迟抛出 `CausalityError`。超出 `maximum_delay_samples` 也明确拒绝。

整数延迟必须零填充，禁止 `np.roll()`。63 抽头分数延迟使用因果窗化 sinc；实现将滤波器固有群时延与粗延迟共同核算，使 `CompiledScatterer` 声明的总延迟是对外可观察的延迟。若给定总延迟不足以容纳因果滤波器支持区间，则拒绝而不是使用未来输入样点。

### 8.4 RCS 数字增益

等效 RCS：

```text
sigma_equivalent = target_rcs * (physical_range / apparent_range)^4
```

数字电压增益相对标定锚点按平方根换算。没有有效 `RcsCalibrationAnchor` 时，只允许相对增益研究，不返回“绝对 RCS 已校准”状态。

`rcs_reference_channel` 指定 `HH/HV/VH/VV` 中哪个矩阵元素对应 `target_rcs_m2`。指定元素必须非零；编译器据此归一化完整散射矩阵并乘以复增益和初相。

### 8.5 `GoldenPolarimetricReflectionKernel`

对每个目标执行：

```text
H/V 输入
  -> 因果整数和分数延迟
  -> 2x2 复散射矩阵
  -> exp(j*2*pi*fD*n/fs) 多普勒旋转
  -> 多目标复数累加
```

多普勒相位使用全局绝对样点 `start_sample + n`，保证分块运行与整段运行在重叠有效区一致。目标按输入顺序计算，但测试使用容差比较浮点结果，不依赖浮点加法的交换律逐位相等。

### 8.6 `GoldenTxPredistorter`

使用 TX 通道复传递矩阵和每路 DAC 校准参数生成预补偿后的 H/V 包络。矩阵求逆前检查秩和条件数；奇异或超出配置条件数上限的标定矩阵明确报错，不静默使用伪逆。

### 8.7 `GoldenEightChannelDacRouter`

将 H/V 预补偿包络路由到实际 DAC 映射：

- 同一极化的高/中/低回波端口接收同一逻辑回波，但分别应用各物理链路的复校准、数字比例和启用状态；
- 未启用端口严格输出零；
- DAC6/7 根据显式模式输出校准包络、外部抵消包络或零；
- 路由器不执行目标物理计算，不运行检测器。

### 8.8 `GoldenReflectionSource`

```python
@dataclass(frozen=True)
class ReflectionSourceResult:
    incident: PolarimetricWaveform
    desired_reflection: PolarimetricWaveform
    actual_uncompensated: PolarimetricWaveform
    predistorted_reflection: PolarimetricWaveform
    dac_frame: EightChannelDacFrame
    pulse_records: tuple[PulseRecord, ...]
    compiled_targets: tuple[CompiledScatterer, ...]
    status: ReflectionStatus
```

`ReflectionStatus` 是不可变状态对象，至少包含：

```text
adc_clipped[2]                 # H/V 是否出现削顶
selected_ranges[2]             # H/V 最终选择档位
absolute_rcs_calibrated        # 是否有有效绝对 RCS 锚点
calibration_out_of_range       # 频率或温度是否超出有效范围
calibration_outputs_enabled
cancellation_outputs_enabled
monitor_pulse_count
```

```python
class GoldenReflectionSource:
    def run(
        self,
        adc_frame: EightChannelAdcFrame,
        scenario: ReflectionScenario,
    ) -> ReflectionSourceResult:
        ...
```

固定执行顺序：

```text
ADC 校准和 H/V 重构
  -> 目标编译
  -> 反射内核
  -> TX 预补偿
  -> DAC 路由
  -> 独立运行监测旁路并合并结果对象
```

监测旁路可以在实现中先运行或后运行，但其输出、门限、事件数量和异常不得改变 `desired_reflection`、`predistorted_reflection` 或 `dac_frame`。监测失败以状态或独立异常报告，禁止默默返回被修改的主链结果。

## 9. 标定语义

Golden 区分三种波形：

1. `desired_reflection`：理想目标在统一 H/V 数学边界上的期望结果；
2. `actual_uncompensated`：可选诊断结果，施加实测 RX/TX 误差；
3. `predistorted_reflection`：数字预补偿后送往 DAC 路由的包络。

标定模型至少表达：

```text
y_actual = C_TX * S * C_RX * x
```

补偿目标：

```text
P_RX * C_RX ~= I
C_TX * P_TX ~= I
```

幅度、相位和相对时延都是标定结果的一部分。单一“固定延迟”不能替代频率和温度相关复传递函数。第一阶段在一个标定频点和温度上运行；输入场景超出配置允许偏差时状态标记为 `calibration_out_of_range`，不宣称绝对指标有效。

## 10. 错误和状态

以下情况必须显式拒绝：

- ADC/DAC/HV 数组维度、长度、采样域或采样率错误；
- 通道映射缺失、重复或极化三量程不完整；
- `FUSED` 模式被启用；
- 目标数量超过上限；
- 表观距离不满足因果性或延迟超过上限；
- 散射矩阵形状错误、含非有限值或 RCS 参考元素为零；
- 标定数组不是 8 路、矩阵奇异或数值条件过差；
- 主链要求绝对 RCS，但标定锚点无效。

以下情况写入 `ReflectionStatus`，但仍可返回数学结果：

- 输入发生削顶并已按配置降档；
- 当前频率或温度超出标定有效范围；
- 只运行相对 RCS 模式；
- DAC 校准/抵消端口被禁用；
- 监测旁路自身没有检出脉冲。

## 11. 测试与验收

### 11.1 公共契约和配置

- H/V、8 路 ADC/DAC 形状和采样域校验；
- 默认通道映射和重复/缺失映射拒绝；
- 两份默认 JSON 逐字节一致；
- 500 MSPS 主链与 250 MSPS 监测旁路关系保持成立。

### 11.2 ADC 前端

- H/V 固定量程互不影响；
- clipping 逐样点传播；
- `AUTO_HOLD` 降档、滞回和最小保持时间；
- 参考通道不参与普通选择；
- 注入幅相/时延误差后能恢复校准波形。

### 11.3 延迟和目标编译

- 单位脉冲输出位置等于编译总延迟；
- 门限变化不改变输出位置；
- 非因果距离抛出 `CausalityError`；
- 分数延迟无首尾循环回绕；
- 多频正弦验证群延迟、幅度和平滑相位；
- 分块处理与整段处理的绝对多普勒相位一致。

### 11.4 极化、RCS和多目标

- H 单输入分别验证 HH 和 VH；
- V 单输入分别验证 HV 和 VV；
- H/V 同时输入验证完整矩阵乘法；
- 相邻样点多普勒相位差为 `2*pi*fD/fs`；
- 表观距离加倍时，等 RCS 功率变为 `1/16`、电压增益变为 `1/4`；
- 多目标结果等于各目标独立结果的容差内复数和。

### 11.5 标定和 DAC 路由

- 注入 RX/TX 复误差后，补偿结果恢复理想 H/V；
- 奇异标定矩阵明确拒绝；
- V 回波只到 DAC0/2/4，H 回波只到 DAC1/3/5；
- DAC6/7 按校准、抵消或关闭模式输出；
- 未启用通道严格为零。

### 11.6 系统和旧功能回归

- 一次调用返回入射波、编译目标、期望回波、预补偿回波、8 路 DAC 帧和监测 PDW；
- 修改检测阈值、禁用检测或没有检出事件，DAC 主链输出保持不变；
- 现有 detector、FIR、clipping、FWHM、LFM、`PulseRecord` 物理格式、采样率和舍入测试全部继续通过。

Golden 验收只证明数学语义。它不证明 Cycle 周期结构、生成 RTL 位精确、Vivado 接口、CDC、时序、RFDC 配置或板上 8 路 RF 性能。

## 12. Golden 实施批次

按以下批次实施，每批都先写失败测试，再实现最小功能并运行全部旧回归：

1. 公共类型、配置分层和实际通道映射；
2. 因果延迟、目标编译和分数延迟；
3. RCS 标定锚点和数字复增益；
4. 2x2 极化、多普勒和多目标内核；
5. 8 路 ADC 校准与量程选择；
6. RX/TX 复标定和预补偿；
7. 8 路 DAC 路由；
8. Golden 系统顶层和检测旁路；
9. 完整回归、README、公共导出和示例。

Golden 完成并经独立评审后，再为 Cycle/RTL 建立新规格，依次设计连续延迟存储、分数延迟 Farrow、多目标吞吐、定点位宽、流水线、跨时钟和 RFDC 端口契约。
