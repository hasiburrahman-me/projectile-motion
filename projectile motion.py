import streamlit as st
import numpy as np
import pandas as pd

# --- Physics Calculation Functions ---
def calculate_trajectory(v0, angle_degrees):
    g = 9.8  # Gravity match with your original code
    angle_radians = np.radians(angle_degrees)
    
    # Calculate initial velocity components
    vx = v0 * np.cos(angle_radians)
    vy0 = v0 * np.sin(angle_radians)  
    
    # Calculate Theoretical Range and Max Height
    range_r = (v0 ** 2 * np.sin(2 * angle_radians)) / g
    max_height = (vy0 ** 2) / (2 * g)
    total_time = (2 * vy0) / g if vy0 > 0 else 0
    
    # Generate data points for the trajectory path plot
    if total_time > 0:
        t_steps = np.linspace(0, total_time, num=100)
        x_points = vx * t_steps
        y_points = (vy0 * t_steps) - (0.5 * g * (t_steps ** 2))
    else:
        x_points = [0.0]
        y_points = [0.0]
        
    return range_r, max_height, x_points, y_points

# --- App Layout ---
def main():
    st.title("🚀 Projectile Motion Simulator")
    st.write("Enter your launch parameters below to calculate the physics and see the motion path.")
    st.markdown("---")
    
    st.header("Input Launch Parameters:")
    
    # User inputs using number input fields (matching your calculator styles)
    velocity = st.number_input("Enter initial velocity (m/s):", min_value=0.0, value=25.0)
    angle = st.number_input("Enter launch angle (degrees):", min_value=0.0, max_value=90.0, value=45.0)
    
    # Button to trigger calculation and chart rendering
    if st.button("Simulate Motion"):
        if velocity <= 0:
            st.warning("Please enter an initial velocity greater than 0.")
        else:
            # 1. Calculate Results
            range_r, max_height, x, y = calculate_trajectory(velocity, angle)
            
            # 2. Display Numerical Outputs
            st.markdown("### Outputs:")
            col1, col2 = st.columns(2)
            with col1:
                st.success(f"Horizontal Range (R): {range_r:.2f} m")
            with col2:
                st.info(f"Max Height (H_max): {max_height:.2f} m")
                
            # 3. Plot the Motion Path (Replacing the canvas)
            st.markdown("### Trajectory Motion Graph:")
            chart_data = pd.DataFrame({
                'Horizontal Distance (m)': x,
                'Vertical Height (m)': y
            })
            
            # Use Streamlit's built-in line chart mapped correctly
            st.line_chart(chart_data, x='Horizontal Distance (m)', y='Vertical Height (m)')

if __name__ == '__main__':
    main()