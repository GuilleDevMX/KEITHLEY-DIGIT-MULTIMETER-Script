/*
 //  Descripción del Código: Coding dojo sobre maquinas de Val
 //
 //          /|\  TIVA C TM4C123G
 //           | ------------------
 //           | |                |-->LED R : PF1
 //           --|RST             |-->LED G : PF3
 //             |                |-->LED B : PF2
 //             |                |
 //             |                |-->SALIDA DIGITAL : PE0
 // PA0 : RX1 o-|                |-->TX    : PA1 Comunicacion a 115200 baudios
 //             |                |
 //             |                |-->Dir:  : PD0 Pin de direccion de giro
 //             |                |-->PWM1  : PB6 Velocidad del motor
  */
//-------------------------------------------------------------------
#include <DeclaracionFunciones.h>
#include <VariablesPrincipal.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include "inc/hw_types.h"
#include "inc/hw_memmap.h"
#include "inc/hw_ssi.h"
#include "driverlib/sysctl.h"
#include "driverlib/gpio.h"
#include "driverlib/uart.h"
#include "driverlib/interrupt.h"
#include "driverlib/pin_map.h"
#include "sensorlib/hw_mpu6050.h"
#include "sensorlib/i2cm_drv.h"
#include "sensorlib/mpu6050.h"
#include "driverlib/timer.h"
#include "driverlib/ssi.h"
#include "utils/uartstdio.h"
// ========================================================
// Variables globales del filtro Kalman 1D
// ========================================================
float A = 1.0f;
float H = 1.0f;
float B = 0.0f;
float Q = 1e-4f;   // varianza del proceso
float R = 1e-2f;   // varianza de la medición

float x_est = 0.0f;  // estado estimado
float P_est = 1.0f;  // varianza inicial
float K = 0.0f;      // ganancia de Kalman
float kalmanOut=0.0f;
// ========================================================
// Inicializa el filtro de Kalman
// ========================================================
void Kalman1D_Init(float x0, float P0, float A_in, float H_in, float B_in, float Q_in, float R_in) {
    x_est = x0;
    P_est = P0;
    A = A_in;
    H = H_in;
    B = B_in;
    Q = Q_in;
    R = R_in;
    K = 0.0f;
}

// ========================================================
// Paso de actualización del filtro (1 dato)
// ========================================================
float Kalman1D_Update(float z, float u) {
    // Predicción
    float x_pred = (A * x_est) + (B * u);
    float P_pred = (A * P_est * A) + Q;

    // Innovación
    float y = z - (H * x_pred);
    float S = (H * P_pred * H) + R;

    // Ganancia de Kalman
    K = (P_pred * H) / S;

    // Corrección
    x_est = x_pred + (K * y);
    P_est = (1.0f - (K * H)) * P_pred;

    return x_est;
}

int main(void)
{
    configuracion();
    freq = SysCtlClockGet();
    Retardo_ms(200);       //Tiempo para estabilizar fuentes de alimentación
    float Vref = 2.5; //Cambia si estás usando otro Vref externo
    float  ganancia = 1.0;      // Según lo que configuraste en el PGA
    float FS = 8388608.0;// Para 24 bits en modo bipolar

    CalibracionADS();
    ConfiguracionADS();
    LuzOff
    Retardo_ms(100);
    // Inicializar Kalman
    Kalman1D_Init(0.0f, 1.0f, 1.0f, 1.0f, 0.0f, 1e-4f, 1e-2f);

    while(1){
            //LuzAmarilla y LuzOff
            if (g_bDRDY_Ready) //Respues del ADS1263 (50 ms, 20 SPS)
              {
                 //Retardo_ms(20);
                 //**********Lectura ADS*******
                 LuzAmarilla
                 g_bDRDY_Ready = false;
                 valor = ADS1263_read_ADC1();
                 valor1 = ADS1263_read_ADC2();
                 //*****************ADC a Volt**************************
                 voltaje1ANT2=voltaje1ANT1;
                 voltaje1ANT1=voltaje1ANT;
                 voltaje1ANT=voltaje1;
                 voltaje1 = (((float)valor / (FS-1)) * (Vref / ganancia))*0.0625;//*0.5 o *0.125;
                 kalmanOut = Kalman1D_Update(voltaje1, 0.0f);
                 voltaje2 = (((float)valor1 / (FS-1)) * (Vref / ganancia));
                 Termo_T = voltaje1;
                 Vin =2.5 - voltaje2;
                 //5072, Alimentacion = 5.0495 V
                 RNTC = (float) 5080  * Vin / (5 - Vin); // RNTC = R1 * Vout/(Vin - Vout)
                 NTC = (float)(1/(1/298.15 + 1/3480.0*log(RNTC/5000.0)))-273.15; // T (°C) = (1/(1/T0 + 1/B*ln(R/R0)))-273.15
                 //Filtro = 0.067455*voltaje1 + 0.134911*voltaje1ANT1 + 0.067455*voltaje1ANT2 - (-1.142981*FiltroANT) - 0.412802*FiltroANT1;
                 //y[n] = 0.067455*x[n] + 0.134911*x[n-1] + 0.067455*x[n-2] - -1.142981*y[n-1] - 0.412802*y[n-2]
                 FiltroANT1=FiltroANT;
                 FiltroANT=Filtro;
                 //voltaje1INT = voltaje1*1000000;
                 doubleToString(voltaje1, buf, 6);
                 doubleToString(NTC, buf2, 2);
                 doubleToString(kalmanOut, Array, 6);
                 //combinado = ((a & 0x0F) << 4) | (b & 0x0F);
                 ///Sin filtro
                 B1 = ((buf[3] & 0x0F) << 4) | (buf[4] & 0x0F);
                 B2 = ((buf[5] & 0x0F) << 4) | (buf[6] & 0x0F);
                 B3 = ((buf[7] & 0x0F) << 4) | (buf[8] & 0x0F);
                 //Con filtro
                 B4 = ((Array[3] & 0x0F) << 4) | (Array[4] & 0x0F);
                 B5 = ((Array[5] & 0x0F) << 4) | (Array[6] & 0x0F);
                 B6 = ((Array[7] & 0x0F) << 4) | (Array[8] & 0x0F);
                 //NTC
                 B7 = ((buf2[1] & 0x0F) << 4) | (buf2[2] & 0x0F);
                 B8 = ((buf2[4] & 0x0F) << 4) | (buf2[5] & 0x0F);
                 ////////////////////
                 UARTCharPut(UART0_BASE, buf[0]);   //0
                 UARTCharPut(UART0_BASE, B1);       //1
                 UARTCharPut(UART0_BASE, B2);       //2
                 UARTCharPut(UART0_BASE, B3);       //3
                 UARTCharPut(UART0_BASE, 'A');      //4
                 UARTCharPut(UART0_BASE, Array[0]); //5
                 UARTCharPut(UART0_BASE, B4);       //6
                 UARTCharPut(UART0_BASE, B5);       //7
                 UARTCharPut(UART0_BASE, B6);       //8
                 UARTCharPut(UART0_BASE, 'B');      //9
                 UARTCharPut(UART0_BASE, B7);       //10
                 UARTCharPut(UART0_BASE, B8);       //11
                 UARTCharPut(UART0_BASE, '\r');     // retorno de carro //12
                 UARTCharPut(UART0_BASE, '\n');     // salto de línea //13
                 //addPrefixSuffix(buf, "ABCD", 'X');    // buf = "ABCD0.00000001X"
                 //UART0_SendString(buf);
                 //UARTCharPut(UART0_BASE, 'A');
                 //addPrefixSuffix(buf2, "ABCD", 'X');    // buf2 = "ABCD0.00000001X"
                 //UART0_SendString(Array2);
                 //SE AGREGO
                 //UARTCharPut(UART0_BASE, 'B');
                 //UART0_SendString(buf2);


                 LuzOff
              }
    }//Fin del while
}//Fin del main
void ConfiguracionADS(void){
    CS_LOW();

    //######ID#######
    SPI0_transfer(0x20);   // Comando: RREG 0x00
    SPI0_transfer(0x00);   // Leer 1 byte
    id1 = SPI0_transfer(0xFF);  // Dummy read

    // === Configuración ADC1 (ejemplo AIN0-AIN1) ===
    SPI0_transfer(0x46);   // WREG INPMUX (0x02)
    SPI0_transfer(0x00);   // 1 byte
    SPI0_transfer(0x01);   // AIN0+, AIN1-


    // === Configuración filtro
    SPI0_transfer(0x44);   // MODE1 (0X04)
    SPI0_transfer(0x00);   // 1 byte
    SPI0_transfer(0x00);    // sinc1
    //SPI0_transfer(0x20);   // sinc2
    //SPI0_transfer(0x40);   // sinc3
    //SPI0_transfer(0x60);   // sinc4
    //SPI0_transfer(0x80); // FIR

    // Configurar PGA en MODE2
    SPI0_transfer(0x43);
    SPI0_transfer(0x00);
    SPI0_transfer(0x10); // Chop=ON

    // === Configuración ADC2 (ejemplo AIN2-AIN3) ===
    SPI0_transfer(0x56);   // WREG INPMUX2 (0x16h)
    SPI0_transfer(0x00);   // 1 byte
    SPI0_transfer(0x23);   // AIN2+, AIN3-

    /*// === Configuración ADC2 Gain,Velocidad
    SPI0_transfer(0x55);   // WREG ADC2CFG (0x15h)
    SPI0_transfer(0x00);   // 1 byte
    SPI0_transfer(0x23);   // gain 1 */

    // Inicia conversiones en ADC1 y ADC2
    SPI0_transfer(0x08);   // START1
    SPI0_transfer(0x0C);   // START2

    CS_HIGH();

}
void CalibracionADS(void){
    uint16_t k=0;
    //********CALIBRAR**************

        CS_LOW();
        // RESET
        SPI0_transfer(0x06);
        // #### INICIA el modo de CONVERSION
        SPI0_transfer(0x43);  // registro MODE2
        SPI0_transfer(0x00);  // 1 byte
        SPI0_transfer(0x10); //cambio de 0x00 a 0x10

        // #### Ganancias
        /*SPI0_transfer(0x25);   // 0x20 (READ) + 0x05 (dirección MODE2)
        SPI0_transfer(0x00);   // Quiero leer solo 1 registro
        MODE2_Valor = SPI0_transfer(0xFF);
        MODE2_Valor &= ~(0x07 << 4);  // limpiar campo PGA
        MODE2_Valor |= (0x11 << 4);   // PGA = 8
        //MODE2_Valor |= (0x01 << 4);   // PGA = 2
        MODE2_Valor = 0x34;
        ValorMonitor=MODE2_Valor;*/

        SPI0_transfer(0x45);  // registro MODE2 (gain, data rate)
        SPI0_transfer(0x00);  // 1 byte
        //SPI0_transfer(0x48);  //gain 16,  400 SPS
        //SPI0_transfer(0x4D);  //gain 16, 14400 SPS
        SPI0_transfer(0x44);  //gain 16, 20 SPS
        //SPI0_transfer(0x34);  //gain 8, 20 SPS
        //SPI0_transfer(0x14);  //gain 2, 20 SPS
        Retardo_ms(1);
        SPI0_transfer(0x25);   // 0x20 (READ) + 0x05 (dirección MODE2)
        SPI0_transfer(0x00);   // Quiero leer solo 1 registro
        MODE2_Valor = SPI0_transfer(0xFF);


        // Configurar REFMUX
        SPI0_transfer(0x4F);
        SPI0_transfer(0x00);
        SPI0_transfer(0x00); // REF interna 2.5V

        // Configurar INPMUX (ejemplo: AIN0-AIN1)
        SPI0_transfer(0x46);
        SPI0_transfer(0x00);
        SPI0_transfer(0xFF);

        // START
        SPI0_transfer(0x08);

        // Self Offset Cal
        SPI0_transfer(0x19);
        g_bDRDY_Ready=false;
        LuzAmarilla
        k=0;
        while(!g_bDRDY_Ready){
            k++;
            if(k >= 6000){ // 30s
                //SPI0_transfer(0x19);
                //g_bDRDY_Ready=true;

            }
            Retardo_ms(5);
        }
        //####CALIBRAR GANACIA

        SPI0_transfer(0x17);
        LuzVerde
        g_bDRDY_Ready=false;
        k=0;
        while(!g_bDRDY_Ready){
            k++;
            if(k >= 6000){
                //SPI0_transfer(0x17);
               // g_bDRDY_Ready=true;
                k=0;
            }
            Retardo_ms(5);
        }
        //*********Leer valores del Registro Offset

         SPI0_transfer(0x27);   // 0x20 (READ) + 0x07 (dirección OFCAL0)
         SPI0_transfer(0x00);
         OFCAL0 = SPI0_transfer(0xFF);

         SPI0_transfer(0x28);   // 0x20 (READ) + 0x03 (dirección OFCAL1)
         SPI0_transfer(0x00);   // Quiero leer solo 1 registro
         OFCAL1 = SPI0_transfer(0xFF);

         SPI0_transfer(0x29);   // 0x20 (READ) + 0x03 (dirección OFCAL2)
         SPI0_transfer(0x00);   // Quiero leer solo 1 registro
         OFCAL2 = SPI0_transfer(0xFF);
         Offset_Registro= ((uint32_t)OFCAL2 << 16) | ((uint32_t)OFCAL1 << 8) | OFCAL0;

         SPI0_transfer(0x2A);   // 0x20 (READ) + 0x07 (dirección OFCAL0)
         SPI0_transfer(0x00);   // Quiero leer solo 1 registro
         FSCAL0 = SPI0_transfer(0xFF);

         SPI0_transfer(0x2B);   // 0x20 (READ) + 0x03 (dirección OFCAL1)
         SPI0_transfer(0x00);   // Quiero leer solo 1 registro
         FSCAL1 = SPI0_transfer(0xFF);

         SPI0_transfer(0x2C);   // 0x20 (READ) + 0x03 (dirección OFCAL2)
         SPI0_transfer(0x00);   // Quiero leer solo 1 registro
         FSCAL2 = SPI0_transfer(0xFF);
         Gain_Cal_Registro= ((uint32_t)FSCAL2 << 16) | ((uint32_t)FSCAL1 << 8) | FSCAL0;

         SPI0_transfer(0x25);   // 0x20 (READ) + 0x05 (dirección MODE2)
         SPI0_transfer(0x00);   // Quiero leer solo 1 registro
         MODE2_Valor = SPI0_transfer(0xFF);

         CS_HIGH();
}

// ==== Enviar una cadena ====
void UART0_SendString(char *str)
{
    while(*str)
    {
        UARTCharPut(UART0_BASE, *str++); //UART0_SendChar(*str++);
    }
}
void addPrefixSuffix(char *buf, const char *prefix, char suffix)
{
    char temp[64];   // buffer temporal (asegúrate que sea suficientemente grande)
    int i, len = 0;//, j = 0;

    // Copiar prefijo (4 letras)
    while(prefix[len] != '\0')
    {
        temp[len] = prefix[len];
        len++;
    }

    // Copiar buf original
    i = 0;
    while(buf[i] != '\0')
    {
        temp[len++] = buf[i++];
    }

    // Agregar sufijo (1 letra)
    temp[len++] = suffix;

    // Terminar con null
    temp[len] = '\0';

    // Copiar de regreso a buf
    i = 0;
    while(temp[i] != '\0')
    {
        buf[i] = temp[i];
        i++;
    }
    buf[i] = '\0';
}
// ==== Convertir double a string sencillo ====
void doubleToString(double num, char *buffer, int decimals)
{
    long entero;
    int i, digit;
    int len = 0;

    // Manejo del signo
    if (num < 0)
    {
        buffer[len++] = '-';
        num = -num; // convertir a positivo para procesar
    }
    else
    {
        buffer[len++] = '+';  // <-- Si NO quieres el '+' para positivos, comenta esta línea
    }

    // Parte entera
    entero = (long)num;

    if (entero == 0)
    {
        buffer[len++] = '0';
    }
    else
    {
        long temp = entero;
        char tempBuf[20];
        int tempLen = 0;

        while (temp > 0)
        {
            tempBuf[tempLen++] = (temp % 10) + '0';
            temp /= 10;
        }

        // Invertir y copiar
        for (i = tempLen - 1; i >= 0; i--)
            buffer[len++] = tempBuf[i];
    }

    buffer[len++] = '.';  // punto decimal

    // Parte decimal
    double frac = num - (double)entero;
    for (i = 0; i < decimals; i++)
    {
        frac *= 10;
        digit = (int)frac;
        buffer[len++] = digit + '0';
        frac -= digit;
    }

    buffer[len] = '\0';  // terminar cadena
}


uint8_t SPI0_transfer(uint8_t data) { //FIJA
    while ((SSI0_SR_R & 0x02) == 0);
    SSI0_DR_R = data;
    while ((SSI0_SR_R & 0x04) == 0);
    return SSI0_DR_R;
}
uint32_t ADS1263_read_ADC1(void){ //FIJA

    // Esperar a que DRDY esté en bajo
    //while (GPIO_PORTB_DATA_R & DRDY_PIN);
    CS_LOW();
    SPI0_transfer(0x12);  // RDATA command

    status = SPI0_transfer(0xFF);  // Leer status
    byte1 = SPI0_transfer(0xFF);   // MSB
    byte2 = SPI0_transfer(0xFF);
    byte3 = SPI0_transfer(0xFF);
    CS_HIGH();
    status=status;

    result = ((uint32_t)byte1 << 16) | ((uint32_t)byte2 << 8) | byte3;

    // Si el dato es negativo (24-bit signed), hacer extensión de signo
    if (result & 0x800000) {
        result |= 0xFF000000;  // Extensión a 32 bits negativo
    }

    return (int32_t)result;
}
uint32_t ADS1263_read_ADC2(void) { //FIJA

    // Esperar a que DRDY esté en bajo
    //while (GPIO_PORTB_DATA_R & DRDY_PIN);
    CS_LOW();
    SPI0_transfer(0x14);  // RDATA command

    status2 = SPI0_transfer(0xFF);  // Leer status
    byte12 = SPI0_transfer(0xFF);   // MSB
    byte22 = SPI0_transfer(0xFF);
    byte32 = SPI0_transfer(0xFF);
    CS_HIGH();
    status2=status2;

    result2 = ((uint32_t)byte12 << 16) | ((uint32_t)byte22 << 8) | byte32;

    // Si el dato es negativo (24-bit signed), hacer extensión de signo
    if (result2 & 0x800000) {
        result2 |= 0xFF000000;  // Extensión a 32 bits negativo
    }

    return (int32_t)result2;
}
void ADS1263_start_conversion(void) { //FIJA NO MOVER
    CS_LOW();
    SPI0_transfer(0x08);  // START command
    CS_HIGH();
}




