#include <cmath>
#include <cstddef>

#if defined(_WIN32)
#define ULTRASOUND_EXPORT __declspec(dllexport)
#else
#define ULTRASOUND_EXPORT
#endif

extern "C" ULTRASOUND_EXPORT int native_openmp_enabled() {
#ifdef _OPENMP
  return 1;
#else
  return 0;
#endif
}

// V2 receives a validated selected angle batch. Python prepares quadrature;
// both components use this float64 focusing kernel.
extern "C" ULTRASOUND_EXPORT void plane_wave_das_v2(
    const double* channels, const double* angles, const double* elements,
    const double* xs, const double* zs, int na, int ne, int ns, int nx, int nz,
    double fs, double speed, double t0, double f_number, int order, int threads,
    double* output) {
  constexpr double pi = 3.14159265358979323846;
#pragma omp parallel for num_threads(threads)
  for (int ix = 0; ix < nx; ++ix) {
    for (int iz = 0; iz < nz; ++iz) {
      const double x = xs[ix], z = zs[iz];
      const double aperture = std::fmax(z / (2 * f_number), 1e-9);
      double total = 0;
      for (int ia = 0; ia < na; ++ia) {
        const double tx = x * std::sin(angles[ia]) + z * std::cos(angles[ia]);
        double numerator = 0, denominator = 0;
        for (int ie = 0; ie < ne; ++ie) {
          const double offset = std::fabs(x-elements[ie]) / aperture;
          if (offset > 1) continue;
          const double position = ((tx + std::hypot(x-elements[ie], z))/speed-t0)*fs;
          // Range check before float-to-int conversion avoids undefined overflow.
          const double first = order == 3 ? 1.0 : 0.0;
          const double stop = order == 3 ? ns-2.0 : ns-1.0;
          if (!std::isfinite(position) || position < first || position >= stop) continue;
          const int lower = static_cast<int>(std::floor(position));
          const double f = position-lower;
          const std::size_t base = (static_cast<std::size_t>(ia)*ne+ie)*ns+lower;
          const double p1 = channels[base], p2 = channels[base+1];
          double delayed = p1*(1-f)+p2*f;
          if (order == 3) {
            const double p0 = channels[base-1], p3 = channels[base+2];
            delayed = p1 + 0.5*f*(p2-p0+f*(2*p0-5*p1+4*p2-p3+f*(3*(p1-p2)+p3-p0)));
          }
          const double weight = 0.5*(1+std::cos(pi*offset));
          numerator += weight*delayed;
          denominator += weight;
        }
        if (denominator > 0) total += numerator/denominator;
      }
      output[static_cast<std::size_t>(iz)*nx+ix] = total/na;
    }
  }
}

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
