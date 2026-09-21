#include <cmath>
#include <cstddef>

#if defined(_WIN32)
#define ULTRASOUND_EXPORT __declspec(dllexport)
#else
#define ULTRASOUND_EXPORT
#endif

extern "C" ULTRASOUND_EXPORT void plane_wave_das(
    const float* channel_data,
    const double* transmit_angles,
    const int* angle_indices,
    const double* element_x,
    const double* x_axis,
    const double* z_axis,
    const int angle_count,
    const int transmit_count,
    const int element_count,
    const int sample_count,
    const int x_count,
    const int z_count,
    const double sampling_frequency,
    const double sound_speed,
    const double initial_time,
    const double f_number,
    double* output) {
  constexpr double pi = 3.14159265358979323846;
#pragma omp parallel for
  for (int x_index = 0; x_index < x_count; ++x_index) {
    const double x = x_axis[x_index];
    for (int z_index = 0; z_index < z_count; ++z_index) {
      const double z = z_axis[z_index];
      const double half_aperture = std::fmax(z / (2.0 * f_number), 1e-9);
      double compounded = 0.0;
      for (int selected = 0; selected < angle_count; ++selected) {
        const int angle_index = angle_indices[selected];
        if (angle_index < 0 || angle_index >= transmit_count) continue;
        const double angle = transmit_angles[angle_index];
        const double transmit = x * std::sin(angle) + z * std::cos(angle);
        double numerator = 0.0;
        double normalizer = 0.0;
        for (int element = 0; element < element_count; ++element) {
          const double offset = std::fabs(element_x[element] - x);
          const double normalized = offset / half_aperture;
          if (normalized > 1.0) continue;
          const double receive = std::hypot(x - element_x[element], z);
          const double position =
              ((transmit + receive) / sound_speed - initial_time) * sampling_frequency;
          const int lower = static_cast<int>(std::floor(position));
          if (lower < 0 || lower + 1 >= sample_count) continue;
          const std::size_t base =
              (static_cast<std::size_t>(angle_index) * element_count + element) * sample_count;
          const double fraction = position - lower;
          const double delayed = channel_data[base + lower] * (1.0 - fraction) +
                                 channel_data[base + lower + 1] * fraction;
          const double weight = 0.5 * (1.0 + std::cos(pi * normalized));
          numerator += delayed * weight;
          normalizer += weight;
        }
        if (normalizer > 0.0) compounded += numerator / normalizer;
      }
      output[static_cast<std::size_t>(z_index) * x_count + x_index] =
          compounded / angle_count;
    }
  }
}
